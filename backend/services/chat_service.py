"""
Khung 1 – người dùng (đặc tả 01 mục 3.1–3.2, đặc tả 03 mục 3).

Luồng một tin nhắn ở chế độ AI:
  lưu tin khách -> phân loại (quy tắc + AG-0)
    ├─ cấp cứu            -> thẻ cấp cứu (mẫu cố định, không qua LLM)
    ├─ không cho AI trả lời -> mời chuyển người trực (mẫu cố định)
    └─ được phép          -> tra tài liệu (RAG) -> AG-1 stream -> lưu câu trả lời + nguồn
"""

from backend.agents import context_builder as ctx
from backend.agents.registry import AG1_USER_AI
from backend.core import iso, utc_now
from backend.domain import (
    AiRun,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    EndUser,
    Message,
    SenderType,
)
from backend.llm.gateway import PRIORITY_INTERACTIVE, LLMError, StreamStats
from backend.services.triage import _max_level, _max_urgency
from rag import rag

EMERGENCY_TEXT = ('Các dấu hiệu bạn mô tả có thể nguy hiểm. Hãy **gọi 115** hoặc đến cơ sở y tế '
                  'gần nhất **ngay**. Bạn cũng có thể chọn "Chat với người trực" để được hướng dẫn '
                  'thêm trong lúc chờ.')
HANDOFF_TEXT = ('Câu hỏi này cần người trực chuyên môn tư vấn theo tình trạng cụ thể của bạn. '
                'Bạn vui lòng chọn "Chat với người trực" để được hỗ trợ.')
AI_UNAVAILABLE_TEXT = ('Hiện AI chưa trả lời được (mô hình đang không khả dụng). Bạn vui lòng chọn '
                       '"Chat với người trực" hoặc thử lại sau.')
QUEUED_TEXT = 'Đã chuyển cuộc trò chuyện sang người trực. Người trực sẽ phản hồi sớm nhất có thể.'


class ChatError(RuntimeError):
    pass


class ChatService:
    def __init__(self, storage, config_service, gateway, triage, index_manager):
        self.storage = storage
        self.config = config_service
        self.gateway = gateway
        self.triage = triage
        self.index = index_manager

    # ---------- cuộc trò chuyện ----------

    def start(self, consent, display_name=None, profile=None):
        if not consent:
            raise ChatError('Cần đồng ý với thông báo trước khi bắt đầu (AC-1.1)')
        now = iso(utc_now())
        user = self.storage.end_users.add(EndUser(display_name=display_name, consent_at=now))
        conversation = Conversation(end_user_id=user.id)
        if profile:
            conversation.profile = conversation.profile.model_validate(profile)
        self.storage.conversations.add(conversation)
        self._event(conversation, 'created', 'end_user', user.id, {'consent_at': now})
        return conversation

    def get(self, conversation_id):
        return self.storage.conversations.get(conversation_id)

    def messages(self, conversation):
        return self.storage.messages.list(conversation.id, conversation.days)

    def update_profile(self, conversation_id, profile):
        conversation = self.get(conversation_id)
        merged = conversation.profile.model_validate({**conversation.profile.model_dump(),
                                                      **{k: v for k, v in profile.items() if v}})
        updated = self.storage.conversations.update(
            conversation.model_copy(update={'profile': merged}), conversation.version)
        self._event(updated, 'profile_edited', 'end_user', conversation.end_user_id, profile)
        return updated

    def handoff(self, conversation_id, reason='user_request'):
        """
        Chuyển sang người trực: vào hàng chờ (phía người trực làm ở P2).

        Returns:
            tuple[Conversation, Message | None]
        """

        conversation = self.get(conversation_id)
        if conversation.mode == 'human':
            return conversation, None
        updated = self.storage.conversations.update(
            conversation.model_copy(update={'mode': 'human', 'status': ConversationStatus.waiting}),
            conversation.version)
        self._event(updated, 'mode_changed', 'end_user', conversation.end_user_id,
                    {'from': 'ai', 'to': 'human', 'reason': reason})
        self._event(updated, 'queued', 'system', None,
                    {'required_level': updated.required_level, 'urgency': updated.urgency})
        message = self._add_message(updated, SenderType.system, QUEUED_TEXT, kind='notice')
        return self.get(conversation_id), message

    # ---------- gửi tin (chế độ AI) ----------

    def send_ai(self, conversation_id, text):
        """
        Generator các sự kiện cho SSE:
          {'type': 'message', 'message': ...}  tin đã lưu (tin khách, thẻ hệ thống)
          {'type': 'triage', ...}
          {'type': 'token', 'text': ...}       chữ của câu trả lời AI
          {'type': 'done', 'message': ...}     câu trả lời AI đã lưu
          {'type': 'error', 'detail': ...}
        """

        text = (text or '').strip()
        if not text:
            raise ChatError('Tin nhắn rỗng')
        conversation = self.get(conversation_id)
        if conversation.mode != 'ai':
            raise ChatError('Cuộc trò chuyện đang ở chế độ người trực')

        history = self.messages(conversation)
        user_message = self._add_message(conversation, SenderType.end_user, text,
                                         sender_id=conversation.end_user_id)
        yield {'type': 'message', 'message': user_message.model_dump(mode='json')}

        outcome = self.triage.classify(
            text, ctx.profile_text(conversation),
            ctx.history_lines(history, ctx.BUDGET['history'] // 4), conversation.id)
        triage = outcome.result
        conversation = self._apply_triage(conversation.id, triage)
        yield {'type': 'triage', 'source': outcome.source, **triage.model_dump()}

        if triage.urgency == 'emergency':
            message = self._add_message(conversation, SenderType.system, EMERGENCY_TEXT,
                                        kind='emergency')
            yield {'type': 'message', 'message': message.model_dump(mode='json')}
            return
        if not triage.ai_allowed:
            message = self._add_message(conversation, SenderType.system, HANDOFF_TEXT,
                                        kind='handoff_suggestion')
            yield {'type': 'message', 'message': message.model_dump(mode='json')}
            return

        yield from self._answer(conversation, history, text, triage)

    def _answer(self, conversation, history, question, triage):
        settings = self.config.settings()
        collection = settings['active_collection']
        retrieval = rag.retrieve(
            question, k=settings['top_k'], history=[m.content for m in history
                                                    if m.sender_type == SenderType.end_user],
            client=self.index.client, use_dense=self.index.has_vectors(collection),
            collection=collection, min_score=settings['min_score'],
            candidate_k=settings['candidate_k'])
        if retrieval.get('warning'):
            yield {'type': 'warning', 'detail': retrieval['warning']}
        blocks = rag.build_context_blocks(retrieval['results'], collection,
                                          max_chars=ctx.chars(ctx.BUDGET['documents']))
        sources = rag.build_sources(blocks)
        documents = rag.format_context(blocks) if blocks else ''

        prompt, version = self.config.prompt(AG1_USER_AI)
        cfg = self.config.agent(AG1_USER_AI)
        messages, estimate = ctx.build_user_ai_messages(prompt, conversation, history, question,
                                                        documents, triage)
        run = AiRun(agent_id=AG1_USER_AI, prompt_version=version, provider=cfg.provider,
                    model=cfg.model, conversation_id=conversation.id,
                    estimated_prompt_tokens=estimate)
        stats = StreamStats()
        parts = []
        try:
            for piece in self.gateway.stream(cfg, messages, PRIORITY_INTERACTIVE, stats):
                parts.append(piece)
                yield {'type': 'token', 'text': piece}
        except LLMError as error:
            run.status, run.error = 'error', str(error)[:500]
            self.storage.ai_runs.add(run)
            if not parts:
                message = self._add_message(conversation, SenderType.system, AI_UNAVAILABLE_TEXT,
                                            kind='handoff_suggestion')
                yield {'type': 'message', 'message': message.model_dump(mode='json')}
                return
            yield {'type': 'error', 'detail': 'Câu trả lời bị gián đoạn'}

        run.provider, run.model = stats.provider or run.provider, stats.model or run.model
        run.duration_s, run.prompt_tokens = stats.duration_s, stats.prompt_tokens
        run.output_tokens = stats.output_tokens
        if run.status == 'ok':
            self.storage.ai_runs.add(run)
        answer = ''.join(parts).strip()
        if answer:
            message = self._add_message(
                conversation, SenderType.ai, answer, ai_run_id=run.id,
                sources=[{k: s[k] for k in ('source_file', 'page', 'page_end', 'title', 'score')}
                         for s in sources])
            yield {'type': 'done', 'message': message.model_dump(mode='json')}

    # ---------- nội bộ ----------

    def _apply_triage(self, conversation_id, triage):
        """Cập nhật cấp cần thiết / độ khẩn: chỉ NÂNG, không bao giờ hạ (BR-08b)."""

        conversation = self.get(conversation_id)
        level = _max_level(conversation.required_level.value, triage.required_level)
        urgency = _max_urgency(conversation.urgency.value, triage.urgency)
        if (level, urgency) == (conversation.required_level.value, conversation.urgency.value):
            return conversation
        return self.storage.conversations.update(
            conversation.model_copy(update={'required_level': level, 'urgency': urgency}),
            conversation.version)

    def _add_message(self, conversation, sender_type, content, sender_id=None, kind='text',
                     sources=None, ai_run_id=None):
        message = Message(conversation_id=conversation.id, sender_type=sender_type,
                          sender_id=sender_id, content=content, kind=kind,
                          sources=sources or [], ai_run_id=ai_run_id)
        self.storage.messages.add(message)
        if message.local_date not in conversation.days:
            fresh = self.get(conversation.id)
            self.storage.conversations.update(
                fresh.model_copy(update={'days': sorted(set(fresh.days) | {message.local_date})}),
                fresh.version)
        return message

    def _event(self, conversation, type_, actor_type, actor_id, data):
        self.storage.events.add(ConversationEvent(conversation_id=conversation.id, type=type_,
                                                  actor_type=actor_type, actor_id=actor_id,
                                                  data=data))
