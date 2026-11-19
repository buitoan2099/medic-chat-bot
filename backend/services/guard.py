"""
Kiểm tra trước khi gửi (đặc tả 03 mục 6, BR-08, BR-08a).

1. Quy tắc (không LLM): rò rỉ trích dẫn; tên thuốc trong danh mục thuốc kê đơn.
2. AG-6 (LLM) đánh giá theo cấp quyền + hồ sơ ca.
3. Chính sách:
   - prescription_drug  -> CHẶN CỨNG ở mọi cấp (không kê đơn trực tuyến).
   - không đủ quyền (guard_hard_issues, mặc định rỗng) -> có thể cấu hình chặn cứng.
0. guard_llm_enabled=False (mặc định): KHÔNG gọi AG-6 – gửi ngay, chỉ còn quy tắc ở mục 1
   (danh mục thuốc kê đơn rỗng thì không chặn được thuốc kê đơn!).
4. Tin người trực TỰ SOẠN (không từ gợi ý AI): người trực trả lời thoải mái – chỉ chặn
   thuốc kê đơn; vấn đề khác (kể cả vượt quyền) chỉ là cảnh báo, không bắt xác nhận.
   guard_llm_for_typed=False: bỏ cả AG-6, chỉ còn quy tắc (gửi ngay, không chờ LLM) – chỉ nên
   tắt khi danh mục thuốc kê đơn (rules/prescription_drugs.json, Q-2) đã đủ.
   Gợi ý AI vượt quyền thì bị chặn ở tầng gửi (operator_service.send), không phụ thuộc AG-6.
   - verdict block khác -> theo cài đặt guard_block_mode: confirm (cần lý do) | hard.
   - AG-6 không chạy được -> chỉ còn quy tắc; cần người trực xác nhận đã tự kiểm tra.
"""

import json
import re

from pydantic import ValidationError

from backend.agents import context_builder as ctx
from backend.agents.registry import AG6_GUARD
from backend.agents.schemas import GuardOutput
from backend.domain import AiRun, GuardCheck
from backend.llm.gateway import PRIORITY_INTERACTIVE, LLMError, record_result
from config import BASE_DIR
from rag.pdf_parser import fold

PRESCRIPTION_FILE = BASE_DIR / 'rules' / 'prescription_drugs.json'

CITATION_PATTERNS = [
    re.compile(r'\.pdf\b', re.IGNORECASE),
    re.compile(r'\btr\.\s*\d+', re.IGNORECASE),
    re.compile(r'\btrang\s+\d+', re.IGNORECASE),
    re.compile(r'\[[^\]\n]{0,80}(trang|tr\.|pdf)[^\]\n]{0,40}\]', re.IGNORECASE),
]

ISSUE_TEXT = {
    'exceeds_level': 'Nội dung vượt phạm vi cấp quyền',
    'prescription_drug': 'Khuyên dùng thuốc kê đơn (không kê đơn trực tuyến)',
    'specific_dose_without_level': 'Đưa liều cho trường hợp cụ thể khi chưa đủ cấp',
    'otc_not_in_list': 'Thuốc không kê đơn ngoài danh sách của tình trạng',
    'missing_max_duration': 'Thiếu thời gian dùng thuốc tối đa trước khi đi khám',
    'missing_monitoring_advice': 'Thiếu hướng dẫn theo dõi / khi nào đi khám',
    'citation_leak': 'Có trích dẫn tài liệu (tên file, số trang) trong tin gửi khách',
    'contraindication_risk': 'Có thể mâu thuẫn với dị ứng / thai kỳ / bệnh nền trong hồ sơ ca',
    'emergency_not_addressed': 'Khách có dấu hiệu cấp cứu nhưng tin chưa hướng dẫn 115 / đi viện',
}


def citation_leak(text):
    return any(p.search(text) for p in CITATION_PATTERNS)


class PrescriptionList:
    def __init__(self, path=PRESCRIPTION_FILE):
        data = json.loads(path.read_text(encoding='utf-8'))
        self.status = data.get('status')
        self.names = [fold(n) for n in data.get('drugs', []) if n.strip()]

    def mentioned(self, text):
        folded = f' {fold(text)} '
        return [n for n in self.names if f' {n} ' in folded]


class GuardService:
    def __init__(self, gateway, config_service, storage, prescriptions=None):
        self.gateway = gateway
        self.config = config_service
        self.storage = storage
        self.prescriptions = prescriptions or PrescriptionList()

    def check(self, conversation, staff_id, level, text, question='', use_llm=True, typed=False):
        rule_issues = []
        if citation_leak(text):
            rule_issues.append('citation_leak')
        suspected = self.prescriptions.mentioned(text)

        if not use_llm:                    # tin tự soạn: chỉ quy tắc, không chờ LLM
            if suspected:
                rule_issues.append('prescription_drug')
            issues = sorted(set(rule_issues))
            hard = 'prescription_drug' in issues
            verdict = 'block' if hard else ('warn' if issues else 'ok')
            check = GuardCheck(conversation_id=conversation.id, staff_id=staff_id, staff_level=level,
                               text=text, verdict=verdict, issues=issues, hard_block=hard,
                               explanation='Tin tự soạn: chỉ kiểm tra theo quy tắc (không dùng AG-6).',
                               llm_available=True)
            return self.storage.guard_checks.add(check)

        llm = None
        llm_available = True
        cfg = self.config.agent(AG6_GUARD)
        prompt, version = self.config.prompt(AG6_GUARD)
        user = (f'CẤP QUYỀN NGƯỜI TRỰC: {level}\n'
                'Hệ thống KHÔNG kê đơn trực tuyến ở mọi cấp (BR-08a).\n\n'
                f'HỒ SƠ CA:\n{ctx.profile_text(conversation) or "(chưa có)"}\n\n'
                f'CÂU HỎI CỦA KHÁCH:\n{question or "(không rõ)"}\n\n'
                + (f'TÊN THUỐC KÊ ĐƠN NGHI VẤN (theo danh mục): {", ".join(suspected)}\n\n'
                   if suspected else '')
                + f'TIN NGƯỜI TRỰC SẮP GỬI:\n{text}\n\n'
                f'Trả về JSON: {json.dumps(GuardOutput.model_json_schema()["properties"], ensure_ascii=False)}')
        run = AiRun(agent_id=AG6_GUARD, prompt_version=version, provider=cfg.provider,
                    model=cfg.model, conversation_id=conversation.id)
        try:
            response = self.gateway.chat(cfg, [{'role': 'system', 'content': prompt},
                                               {'role': 'user', 'content': user}],
                                         PRIORITY_INTERACTIVE, schema=GuardOutput.model_json_schema())
            record_result(run, response)
            llm = GuardOutput.model_validate_json(response.text)
        except (LLMError, ValidationError, ValueError) as error:
            llm_available = False
            run.status, run.error = 'fallback', str(error)[:500]
        self.storage.ai_runs.add(run)

        issues = sorted(set(rule_issues) | set(llm.issues if llm else []))
        verdict = llm.verdict if llm else 'ok'
        if 'citation_leak' in issues and verdict == 'ok':
            verdict = 'warn'
        settings = self.config.settings()
        hard_issues = {'prescription_drug'} | set(settings.get('guard_hard_issues') or [])
        if ({'exceeds_level', 'emergency_not_addressed'} | hard_issues) & set(issues):
            verdict = 'block'
        hard = bool(hard_issues & set(issues)) or (
            verdict == 'block' and settings['guard_block_mode'] == 'hard')
        if typed:                          # tin tự soạn: chỉ thuốc kê đơn là chặn
            hard = 'prescription_drug' in issues
            if not hard:
                verdict = 'warn' if issues else 'ok'

        explanation = llm.explanation if llm else 'AG-6 không khả dụng: chỉ kiểm tra theo quy tắc.'
        check = GuardCheck(conversation_id=conversation.id, staff_id=staff_id, staff_level=level,
                           text=text, verdict=verdict, issues=issues, explanation=explanation,
                           hard_block=hard, llm_available=llm_available)
        return self.storage.guard_checks.add(check)

    def needs_confirmation(self, check):
        if check.hard_block:
            return False
        if check.verdict == 'block':
            return True
        return (not check.llm_available
                and self.config.settings()['guard_confirm_when_unavailable'])

    @staticmethod
    def describe(check):
        return [ISSUE_TEXT.get(i, i) for i in check.issues]
