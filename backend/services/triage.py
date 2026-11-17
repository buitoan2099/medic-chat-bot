"""
Phân loại câu hỏi (AG-0) = quy tắc + LLM (technical plan 5.4).

1. Quy tắc cấp cứu tối thiểu (rules/emergency_minimal.json) – luôn chạy, không cần LLM.
2. LLM AG-0 trả đầu ra có cấu trúc.
3. Lấy mức CAO hơn giữa quy tắc và LLM; không bao giờ hạ tầng (BR-08b).
Lỗi / quá thời gian -> mặc định an toàn: C2, không cho AI trả lời (NFR-2).
"""

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from backend.agents.registry import AG0_TRIAGE
from backend.domain import LEVEL_ORDER, URGENCY_ORDER, AiRun, Level, Urgency
from backend.llm.gateway import PRIORITY_TRIAGE, LLMError
from config import BASE_DIR
from rag.pdf_parser import fold, nfc

RULES_FILE = BASE_DIR / 'rules' / 'emergency_minimal.json'


class TriageResult(BaseModel):
    intent: Literal['drug_info', 'disease_info', 'symptom_assessment', 'treatment_request',
                    'regimen_request', 'admin', 'other']
    required_level: Literal['none', 'C1', 'C2', 'C3']
    urgency: Literal['normal', 'soon', 'emergency']
    emergency_signs: list[str] = Field(default_factory=list)
    ai_allowed: bool
    reason: str = ''


class TriageOutcome(BaseModel):
    result: TriageResult
    source: str                       # rules | llm | rules+llm | fallback
    rule_hits: list[str] = Field(default_factory=list)
    error: Optional[str] = None


SAFE_DEFAULT = TriageResult(intent='other', required_level='C2', urgency='normal',
                            ai_allowed=False,
                            reason='Mặc định an toàn: không phân loại được, chuyển người trực.')


class EmergencyRules:
    def __init__(self, path=RULES_FILE):
        data = json.loads(path.read_text(encoding='utf-8'))
        self.version = data.get('version')
        self.phrases = [nfc(p).lower() for p in data['phrases']]

    def hits(self, text):
        lowered = nfc(text).lower()
        folded = f' {fold(text)} '
        found = []
        for phrase in self.phrases:
            if re.search(rf'(?<!\w){re.escape(phrase)}(?!\w)', lowered):
                found.append(phrase)
            elif ' ' in phrase and f' {fold(phrase)} ' in folded:   # gõ không dấu, cụm ≥ 2 từ
                found.append(phrase)
        return found


def _max_level(a, b):
    return a if LEVEL_ORDER[Level(a)] >= LEVEL_ORDER[Level(b)] else b


def _max_urgency(a, b):
    return a if URGENCY_ORDER[Urgency(a)] >= URGENCY_ORDER[Urgency(b)] else b


class TriageService:
    def __init__(self, gateway, config_service, storage, rules=None):
        self.gateway = gateway
        self.config = config_service
        self.storage = storage
        self.rules = rules or EmergencyRules()

    def _messages(self, question, profile_text, history_text):
        prompt, version = self.config.prompt(AG0_TRIAGE)
        schema_hint = json.dumps(TriageResult.model_json_schema()['properties'], ensure_ascii=False)
        user = (f'HỒ SƠ CA:\n{profile_text or "(chưa có)"}\n\n'
                f'LỊCH SỬ GẦN NHẤT:\n{history_text or "(chưa có)"}\n\n'
                f'TIN NHẮN MỚI NHẤT CỦA KHÁCH:\n{question}\n\n'
                f'Trả về JSON với các trường: {schema_hint}')
        return [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': user}], version

    def classify(self, question, profile_text='', history_text='', conversation_id=None):
        hits = self.rules.hits(question)
        cfg = self.config.agent(AG0_TRIAGE)
        messages, version = self._messages(question, profile_text, history_text)
        run = AiRun(agent_id=AG0_TRIAGE, prompt_version=version, provider=cfg.provider,
                    model=cfg.model, conversation_id=conversation_id)

        llm_result, error = None, None
        try:
            response = self.gateway.chat(cfg, messages, PRIORITY_TRIAGE,
                                         schema=TriageResult.model_json_schema())
            run.provider, run.model = response.provider, response.model
            run.duration_s, run.prompt_tokens = response.duration_s, response.prompt_tokens
            run.output_tokens = response.output_tokens
            llm_result = TriageResult.model_validate_json(response.text)
        except (LLMError, ValidationError, ValueError) as exc:
            error = f'{type(exc).__name__}: {exc}'[:500]
            run.status, run.error = 'fallback', error
        self.storage.ai_runs.add(run)

        if llm_result is None:
            result = SAFE_DEFAULT.model_copy()
            source = 'fallback'
        else:
            result = llm_result
            source = 'llm'

        if hits:
            result = result.model_copy(update={
                'urgency': 'emergency',
                'required_level': _max_level(result.required_level, 'C1'),
                'emergency_signs': sorted(set(result.emergency_signs) | set(hits)),
                'ai_allowed': False,
            })
            source = 'rules' if llm_result is None else 'rules+llm'

        if result.urgency == 'emergency' or result.required_level != 'none':
            result = result.model_copy(update={'ai_allowed': False})

        return TriageOutcome(result=result, source=source, rule_hits=hits, error=error)


__all__ = ['TriageService', 'TriageResult', 'TriageOutcome', 'EmergencyRules', 'SAFE_DEFAULT',
           '_max_level', '_max_urgency']
