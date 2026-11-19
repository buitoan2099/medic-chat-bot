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
from backend.services.mutate import mutate
from backend.services.topic import start_new_topic, topic_messages
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
    def __init__(self, storage, config_service, gateway, triage, index_manager, operator=None,
                 case_memory=None, background=None):
        self.storage = storage
        self.config = config_service
        self.gateway = gateway
        self.triage = triage
        self.index = index_manager
        self.operator = operator            # OperatorService (P2), gán sau khi khởi tạo
        self.case_memory = case_memory
        self.background = background

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
        changes = {k: v for k, v in profile.items() if v}

        def change(conversation):
            merged = conversation.profile.model_validate({**conversation.profile.model_dump(),
                                                          **changes})
            sources = {**conversation.profile_sources, **{k: 'user' for k in changes}}
            return {'profile': merged, 'profile_sources': sources}

        updated = mutate(self.storage, conversation_id, change)
        self._event(updated, 'profile_edited', 'end_user', updated.end_user_id, profile)
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
        now = iso(utc_now())
        updated = mutate(self.storage, conversation_id, lambda c: None if c.mode == 'human' else {
            'mode': 'human', 'status': ConversationStatus.waiting, 'queued_at': now})
        self._event(updated, 'mode_changed', 'end_user', conversation.end_user_id,
                    {'from': 'ai', 'to': 'human', 'reason': reason})
        self._event(updated, 'queued', 'system', None,
                    {'required_level': updated.required_level, 'urgency': updated.urgency})
        message = self._add_message(updated, SenderType.system, QUEUED_TEXT, kind='notice')
        # Hồ sơ ca + tóm tắt cho người trực: chạy MỘT lần khi chuyển, không chạy sau mỗi tin ở
        # chế độ AI (Ollama xử lý tuần tự – chạy nền liên tục làm phân loại phải xếp hàng).
        if self.case_memory is not None and self.background is not None:
            self.background.submit(self.case_memory.update, conversation_id)
        return self.get(conversation_id), message

    # ---------- gửi tin ----------

    def send(self, conversation_id, text):
        """Điều phối theo chế độ: AI -> send_ai; người trực -> chuyển cho người trực."""

        conversation = self.get(conversation_id)
        if conversation.mode == 'ai':
            yield from self.send_ai(conversation_id, text)
            return
        text = (text or '').strip()
        if not text:
            raise ChatError('Tin nhắn rỗng')
        if self.operator is None:
            raise ChatError('Chế độ người trực chưa sẵn sàng')
        new_id, message = self.operator.customer_message(conversation_id, text)
        if new_id != conversation_id:
            yield {'type': 'conversation', 'id': new_id,
                   'detail': 'Cuộc trò chuyện cũ đã quá 24 giờ, đã mở cuộc trò chuyện mới.'}
        yield {'type': 'message', 'message': message.model_dump(mode='json')}

    # ---------- gửi tin (chế độ AI) ----------

    def send_ai(self, conversation_id, text):
        """
        Generator các sự kiện cho SSE:
          {'type': 'message', 'message': ...}  tin đã lưu (tin khách, thẻ hệ thống)
          {'type': 'status', 'stage': ...}     bước đang chạy: classifying | searching | generating
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

        history = topic_messages(conversation, self.messages(conversation))
        user_message = self._add_message(conversation, SenderType.end_user, text,
                                         sender_id=conversation.end_user_id)
        yield {'type': 'message', 'message': user_message.model_dump(mode='json')}

        yield {'type': 'status', 'stage': 'classifying'}
        outcome = self.triage.classify(
            text, ctx.profile_text(conversation),
            ctx.history_lines(history, ctx.BUDGET['history'] // 4), conversation.id)
        triage = outcome.result
        conversation = self._apply_triage(conversation.id, triage)
        if triage.new_topic and any(m.sender_type == SenderType.end_user for m in history):
            # Khách chuyển sang hỏi vấn đề khác: bỏ bệnh cũ khỏi ngữ cảnh của AI
            conversation = start_new_topic(self.storage, conversation.id, user_message.id, 'system',
                                           reason=triage.reason) or self.get(conversation.id)
            history = []
            yield {'type': 'topic_changed'}
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
        yield {'type': 'status', 'stage': 'searching'}
        retrieval = rag.retrieve(
            question, k=settings['top_k'],
            history=[m.content for m in history if m.sender_type == SenderType.end_user],
            client=self.index.client, use_dense=self.index.has_vectors(collection),
            collection=collection, min_score=settings['min_score'],
            candidate_k=settings['candidate_k'], bm25_weights=self.config.bm25_weights())
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
        yield {'type': 'status', 'stage': 'generating'}
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
        run.queue_wait_s = stats.queue_wait_s
        if stats.used_fallback:
            run.status = 'fallback'
            run.error = f'Model chính lỗi, đã dùng dự phòng: {stats.fallback_reason}'[:500]
        run.output_tokens = stats.output_tokens
        if run.status in ('ok', 'fallback'):
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

        def change(conversation):
            level = _max_level(conversation.required_level.value, triage.required_level)
            urgency = _max_urgency(conversation.urgency.value, triage.urgency)
            if (level, urgency) == (conversation.required_level.value, conversation.urgency.value):
                return None
            return {'required_level': level, 'urgency': urgency}

        return mutate(self.storage, conversation_id, change)

    def _add_message(self, conversation, sender_type, content, sender_id=None, kind='text',
                     sources=None, ai_run_id=None):
        message = Message(conversation_id=conversation.id, sender_type=sender_type,
                          sender_id=sender_id, content=content, kind=kind,
                          sources=sources or [], ai_run_id=ai_run_id)
        self.storage.messages.add(message)
        mutate(self.storage, conversation.id, lambda c: None if message.local_date in c.days
               else {'days': sorted(set(c.days) | {message.local_date})})
        return message

    def _event(self, conversation, type_, actor_type, actor_id, data):
        self.storage.events.add(ConversationEvent(conversation_id=conversation.id, type=type_,
                                                  actor_type=actor_type, actor_id=actor_id,
                                                  data=data))
