"""
Copilot cho người trực (AG-2/3/4 theo cấp) và tóm tắt/hồ sơ ca (AG-5).

Copilot: dựa trên HỒ SƠ CA + TÓM TẮT + LỊCH SỬ (gồm cả phần chat với AI) + TÀI LIỆU,
soạn bản nháp KHÔNG trích dẫn cho khách; nguồn chỉ nằm ở phần nội bộ (BR-08, BR-09).
"""

import json
import threading

from pydantic import ValidationError

from backend.agents import context_builder as ctx
from backend.agents.registry import AG5_CASE_MEMORY, COPILOT_BY_LEVEL
from backend.agents.schemas import CaseMemoryOutput, CopilotOutput
from backend.core import utc_now
from backend.domain import AiRun, AiSuggestion, CaseProfile, SenderType
from backend.llm.gateway import PRIORITY_BACKGROUND, PRIORITY_COPILOT, LLMError, record_result
from backend.services.guard import citation_leak
from backend.services.mutate import mutate
from backend.services.topic import start_new_topic, topic_messages
from rag import rag


def _schema_hint(model):
    return json.dumps(model.model_json_schema(), ensure_ascii=False)


class CopilotService:
    def __init__(self, gateway, config_service, storage, index_manager):
        self.gateway = gateway
        self.config = config_service
        self.storage = storage
        self.index = index_manager
        self._locks = {}
        self._guard = threading.Lock()
        self._pending = {}           # conversation_id -> [số việc đang chờ/chạy, thời điểm bắt đầu]

    def _lock(self, conversation_id):
        with self._guard:
            return self._locks.setdefault(conversation_id, threading.Lock())

    def mark_pending(self, conversation_id):
        """Gọi khi xếp lịch tạo gợi ý: giao diện hiện 'đang tạo' kèm thời gian chờ."""
        with self._guard:
            entry = self._pending.setdefault(conversation_id, [0, utc_now()])
            entry[0] += 1

    def _done(self, conversation_id):
        with self._guard:
            entry = self._pending.get(conversation_id)
            if entry:
                entry[0] -= 1
                if entry[0] <= 0:
                    del self._pending[conversation_id]

    def pending_since(self, conversation_id):
        with self._guard:
            entry = self._pending.get(conversation_id)
            return entry[1] if entry else None

    def latest(self, conversation):
        found = self.storage.suggestions.for_conversation(conversation.id, conversation.days)
        return found[-1] if found else None

    def _documents(self, conversation, question):
        settings = self.config.settings()
        collection = settings['active_collection']
        profile = conversation.profile
        # Chỉ ghép triệu chứng chính khi khách đang HỎI TIẾP; câu tự đủ nghĩa (thường là vấn đề
        # mới) tìm theo chính nó, để bệnh cũ không kéo tài liệu sai vào gợi ý.
        carry = profile.chief_complaint if rag.is_follow_up(question) else None
        query = ' '.join(x for x in (question, carry) if x)
        retrieval = rag.retrieve(question, k=settings['top_k'], client=self.index.client,
                                 bm25_weights=self.config.bm25_weights(),
                                 use_dense=self.index.has_vectors(collection), collection=collection,
                                 query_override=query, min_score=None,
                                 candidate_k=settings['candidate_k'])
        blocks = rag.build_context_blocks(retrieval['results'], collection,
                                          max_chars=ctx.chars(ctx.BUDGET['documents']))
        return rag.format_context(blocks) if blocks else '', rag.build_sources(blocks)

    def generate(self, conversation_id, staff_id, level, instruction=None):
        """Sinh gợi ý cho tin khách mới nhất. Gợi ý cũ chưa dùng -> 'superseded'."""

        try:
            with self._guard:              # còn lượt mới hơn đang xếp hàng -> lượt này thừa, bỏ
                queued = self._pending.get(conversation_id, [0])[0]
            if queued > 1 and not instruction:
                return None
            return self._generate(conversation_id, staff_id, level, instruction)
        finally:
            self._done(conversation_id)

    def _already_done(self, conversation, question_id, staff_id):
        """Đã có gợi ý (chưa dùng) cho đúng tin khách này, cùng người trực -> không tạo lại."""
        latest = self.latest(conversation)
        return (latest is not None and latest.for_message_id == question_id
                and latest.staff_id == staff_id and latest.status == 'ready' and latest.outcome is None)

    def _generate(self, conversation_id, staff_id, level, instruction=None):
        with self._lock(conversation_id):
            conversation = self.storage.conversations.get(conversation_id)
            messages = topic_messages(conversation,
                                      self.storage.messages.list(conversation.id, conversation.days))
            customer = [m for m in messages if m.sender_type == SenderType.end_user]
            if not customer:
                return None
            question = customer[-1]
            earlier_customer = len(customer) > 1      # có chủ đề trước trong phạm vi đang đọc
            if not instruction and self._already_done(conversation, question.id, staff_id):
                return self.latest(conversation)
            agent_id = COPILOT_BY_LEVEL[level]
            cfg = self.config.agent(agent_id)
            prompt, version = self.config.prompt(agent_id)

            documents, sources = self._documents(conversation, question.content)
            blocks = [
                f'HỒ SƠ CA:\n{ctx.profile_text(conversation) or "(chưa có)"}',
                f'LỊCH SỬ GẦN NHẤT:\n{ctx.history_lines(messages[:-1] if messages[-1].id == question.id else messages, ctx.BUDGET["history"])}',
                f'TÀI LIỆU:\n{ctx.truncate(documents or "(không tìm thấy đoạn liên quan)", ctx.BUDGET["documents"])}',
                f'CÂU HỎI HIỆN TẠI:\n{ctx.truncate(question.content, ctx.BUDGET["question"])}',
            ]
            if instruction:
                blocks.append('CHỈ DẪN CỦA NGƯỜI TRỰC (không được ghi đè phạm vi cấp quyền và '
                              f'khối an toàn): {instruction}')
            if earlier_customer:
                blocks.append('ĐỔI CHỦ ĐỀ: nếu CÂU HỎI HIỆN TẠI hỏi về bệnh / triệu chứng / thuốc KHÁC '
                              'hẳn vấn đề trong lịch sử (không phải hỏi tiếp hay bổ sung), đặt '
                              'topic_changed = true và CHỈ trả lời câu hỏi mới: bỏ qua bệnh cũ trong '
                              'hồ sơ ca và lịch sử (vẫn dùng thông tin về người: tuổi, dị ứng, bệnh nền, '
                              'thuốc đang dùng, mang thai).')
            blocks.append(f'Trả về JSON đúng lược đồ: {_schema_hint(CopilotOutput)}')
            llm_messages = [{'role': 'system', 'content': prompt},
                            {'role': 'user', 'content': '\n\n'.join(blocks)}]

            suggestion = AiSuggestion(conversation_id=conversation.id, for_message_id=question.id,
                                      staff_id=staff_id, staff_level=level, agent_id=agent_id,
                                      prompt_version=version, model=cfg.model,
                                      regenerate_instruction=instruction,
                                      sources=[{k: s[k] for k in ('source_file', 'page', 'page_end',
                                                                  'title', 'score')}
                                               | {'excerpt': s['excerpt'][:400]} for s in sources])
            run = AiRun(agent_id=agent_id, prompt_version=version, provider=cfg.provider,
                        model=cfg.model, conversation_id=conversation.id,
                        estimated_prompt_tokens=sum(ctx.tokens(m['content']) for m in llm_messages))
            try:
                response = self.gateway.chat(cfg, llm_messages, PRIORITY_COPILOT,
                                             schema=CopilotOutput.model_json_schema())
                output = CopilotOutput.model_validate_json(response.text)
                record_result(run, response)
                suggestion.model, suggestion.used_fallback = response.model, response.used_fallback
                if output.topic_changed and earlier_customer:
                    start_new_topic(self.storage, conversation.id, question.id, 'ai',
                                    reason=f'{agent_id} nhận thấy khách hỏi vấn đề mới')
                suggestion = suggestion.model_copy(update={
                    **output.model_dump(exclude={'scope_check', 'confidence_reason', 'topic_changed'}),
                    'scope_check': output.scope_check.model_dump(),
                    'confidence': output.confidence + (f' – {output.confidence_reason}'
                                                       if output.confidence_reason else '')})
                if citation_leak(suggestion.reply_draft):
                    suggestion.internal_notes = ('⚠ Bản nháp có dấu hiệu trích dẫn tài liệu, cần bỏ '
                                                 'trước khi gửi. ' + suggestion.internal_notes)
            except (LLMError, ValidationError, ValueError) as error:
                suggestion.status, suggestion.error = 'error', str(error)[:500]
                run.status, run.error = 'error', str(error)[:500]
            self.storage.ai_runs.add(run)

            for old in self.storage.suggestions.for_conversation(conversation.id, conversation.days):
                if old.outcome is None and old.status == 'ready':
                    old.outcome = 'superseded'
                    self.storage.suggestions.update(old)
            return self.storage.suggestions.add(suggestion)


class CaseMemoryService:
    """AG-5: cập nhật hồ sơ ca + tóm tắt sau mỗi tin của khách (chạy nền)."""

    def __init__(self, gateway, config_service, storage):
        self.gateway = gateway
        self.config = config_service
        self.storage = storage
        self._locks = {}
        self._guard = threading.Lock()

    def update(self, conversation_id):
        with self._guard:
            lock = self._locks.setdefault(conversation_id, threading.Lock())
        if not lock.acquire(blocking=False):
            return None                      # đang chạy cho cuộc chat này; lần sau sẽ gộp
        try:
            conversation = self.storage.conversations.get(conversation_id)
            messages = self.storage.messages.list(conversation.id, conversation.days)
            new = [m for m in topic_messages(conversation, messages)
                   if conversation.case_memory_upto is None or m.id > conversation.case_memory_upto]
            if not any(m.sender_type == SenderType.end_user for m in new):
                return None
            cfg = self.config.agent(AG5_CASE_MEMORY)
            prompt, version = self.config.prompt(AG5_CASE_MEMORY)
            user = (f'HỒ SƠ CA HIỆN TẠI (JSON): {conversation.profile.model_dump_json()}\n'
                    f'TRƯỜNG DO NGƯỜI TRỰC SỬA (giữ nguyên): '
                    f'{[k for k, v in conversation.profile_sources.items() if v == "staff"]}\n'
                    f'TÓM TẮT HIỆN TẠI: {conversation.summary or "(chưa có)"}\n\n'
                    f'TIN NHẮN MỚI:\n{ctx.history_lines(new, ctx.BUDGET["history"])}\n\n'
                    f'Trả về JSON đúng lược đồ: {_schema_hint(CaseMemoryOutput)}')
            run = AiRun(agent_id=AG5_CASE_MEMORY, prompt_version=version, provider=cfg.provider,
                        model=cfg.model, conversation_id=conversation.id)
            try:
                response = self.gateway.chat(cfg, [{'role': 'system', 'content': prompt},
                                                   {'role': 'user', 'content': user}],
                                             PRIORITY_BACKGROUND,
                                             schema=CaseMemoryOutput.model_json_schema())
                output = CaseMemoryOutput.model_validate_json(response.text)
                record_result(run, response)
            except (LLMError, ValidationError, ValueError) as error:
                run.status, run.error = 'error', str(error)[:500]
                self.storage.ai_runs.add(run)
                return None
            self.storage.ai_runs.add(run)
            return self._merge(conversation.id, output, new[-1].id)
        finally:
            lock.release()

    def _merge(self, conversation_id, output, upto):
        def change(conversation):
            profile = conversation.profile.model_dump()
            sources = dict(conversation.profile_sources)
            for key, value in output.profile.model_dump().items():
                # Trường người trực đã sửa luôn được ưu tiên, AI không ghi đè
                if value and sources.get(key) != 'staff' and value != profile.get(key):
                    profile[key] = value
                    sources[key] = 'ai'
            profile['needs_confirmation'] = output.needs_confirmation
            return {'profile': CaseProfile.model_validate(profile), 'profile_sources': sources,
                    'summary': output.summary or conversation.summary, 'case_memory_upto': upto}

        return mutate(self.storage, conversation_id, change)
