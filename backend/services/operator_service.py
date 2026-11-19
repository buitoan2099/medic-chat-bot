"""
Nghiệp vụ người trực (đặc tả 01 mục 3.3–3.4, BR-01…BR-09).

Mọi thay đổi cuộc chat đi qua mutate() (khoá lạc quan + thử lại) và sinh một
ConversationEvent (BR-07) – nguồn dữ liệu tính hiệu suất ở P3.
"""

import difflib
import threading
from datetime import timedelta

from backend.core import iso, parse_iso, utc_now
from backend.domain import (
    URGENCY_ORDER,
    AuditLog,
    ConversationEvent,
    ConversationStatus,
    Message,
    SenderType,
    Urgency,
)
from backend.services.mutate import Rejected, mutate
from backend.services.permissions import PermissionError_, level_value
from backend.storage.base import ConflictError

CLAIMED_TEXT = '{name} đã tiếp nhận cuộc trò chuyện.'
TAKEN_OVER_TEXT = '{name} sẽ tiếp tục hỗ trợ bạn trong cuộc trò chuyện này.'
ESCALATED_TEXT = 'Câu hỏi của bạn đang được chuyển tới chuyên viên phù hợp hơn. Vui lòng chờ trong giây lát.'
CLOSED_TEXT = 'Cuộc trò chuyện đã kết thúc. Bạn có thể nhắn tiếp trong 24 giờ để được hỗ trợ thêm.'
RETURNED_TEXT = 'Người trực vừa rời ca, cuộc trò chuyện đang được chuyển cho người trực khác.'


class OperatorError(RuntimeError):
    pass


def _min_level(required):
    """Cấp tối thiểu để xử lý: cuộc chat 'none' vẫn cần ít nhất C1."""
    return 'C1' if required in ('none', None) else required


class OperatorService:
    def __init__(self, storage, permissions, config_service, copilot, case_memory, guard,
                 background):
        self.storage = storage
        self.permissions = permissions
        self.config = config_service
        self.copilot = copilot
        self.case_memory = case_memory
        self.guard = guard
        self.background = background            # executor chạy nền (copilot, AG-5)

    # ---------- tiện ích ----------

    def _staff_view(self, staff_id):
        staff = self.storage.staff.get(staff_id)
        eff = self.permissions.effective(staff_id)
        return staff, eff

    def display_name(self, staff):
        return f'{staff.title} {staff.display_name}'.strip()

    def _event(self, conversation_id, type_, actor_id, data=None, actor_type='staff'):
        self.storage.events.add(ConversationEvent(conversation_id=conversation_id, type=type_,
                                                  actor_type=actor_type, actor_id=actor_id,
                                                  data=data or {}))

    def _message(self, conversation_id, sender_type, content, **fields):
        message = Message(conversation_id=conversation_id, sender_type=sender_type,
                          content=content, **fields)
        self.storage.messages.add(message)
        mutate(self.storage, conversation_id, lambda c: None if message.local_date in c.days
               else {'days': sorted(set(c.days) | {message.local_date})})
        return message

    def _active_count(self, staff_id):
        return sum(1 for c in self.storage.conversations.find(status='assigned')
                   if c.assignee_id == staff_id)

    def _can_take(self, staff_id, required, check_presence=True):
        """(được không, lý do) để nhân sự nhận thêm một cuộc chat ở cấp required."""

        staff, eff = self._staff_view(staff_id)
        if not staff.active:
            return False, 'tài khoản đã khoá'
        if check_presence and self.permissions.presence(staff_id) != 'online':
            return False, 'không ở trạng thái đang trực'
        if level_value(eff['level']) < level_value(_min_level(required)):
            return False, f'cấp {eff["level"]} thấp hơn cấp cần thiết {required}'
        if self._active_count(staff_id) >= eff['capabilities']['chat.max_concurrent']:
            return False, 'đã đủ số cuộc chat tối đa'
        return True, ''

    def schedule(self, fn, *args):
        self.background.submit(fn, *args)

    def schedule_copilot(self, conversation_id, staff_id, instruction=None, then=None):
        """Xếp lịch tạo gợi ý; `then` (vd cập nhật hồ sơ ca) chạy SAU khi gợi ý xong, cùng luồng –
        để việc nền không chiếm Ollama trước gợi ý (cả bước embedding tìm tài liệu)."""
        staff, eff = self._staff_view(staff_id)
        if eff['capabilities']['ai.use_copilot'] and eff['level'] in ('C1', 'C2', 'C3'):
            self.copilot.mark_pending(conversation_id)

            def job():
                try:
                    self.copilot.generate(conversation_id, staff_id, eff['level'], instruction)
                finally:
                    if then:
                        then()

            self.schedule(job)
        elif then:
            self.schedule(then)

    # ---------- danh sách ----------

    def queue(self, staff_id):
        """Hàng chờ: chỉ cuộc chat đủ cấp với người trực (BR-02); khẩn trước, chờ lâu trước."""

        staff, eff = self._staff_view(staff_id)
        is_manager = 'manager' in staff.roles
        now = utc_now()
        items = []
        for conversation in self.storage.conversations.find(status='waiting'):
            if not is_manager and level_value(eff['level']) < level_value(
                    _min_level(conversation.required_level.value)):
                continue
            waited = (now - parse_iso(conversation.queued_at or conversation.created_at)).total_seconds()
            items.append({'conversation': conversation, 'waited_s': waited,
                          'sla_breached': conversation.sla_breached_at is not None})
        items.sort(key=lambda i: (-URGENCY_ORDER[i['conversation'].urgency], -i['waited_s']))
        return items

    def mine(self, staff_id):
        assigned = [c for c in self.storage.conversations.find(status='assigned')
                    if c.assignee_id == staff_id]
        offered = [c for c in self.storage.conversations.find()
                   if c.pending_transfer and c.pending_transfer.get('to') == staff_id]
        return {'assigned': assigned, 'transfer_offers': offered}

    def view(self, staff_id, conversation_id):
        staff, eff = self._staff_view(staff_id)
        conversation = self.storage.conversations.get(conversation_id)
        offered = conversation.pending_transfer and conversation.pending_transfer.get('to') == staff_id
        is_owner = conversation.assignee_id == staff_id
        can_view = (is_owner or offered or conversation.status == 'waiting'
                    or eff['capabilities']['chat.view_all'] or 'manager' in staff.roles)
        if not can_view:
            raise PermissionError_('Không có quyền xem cuộc chat này')
        if not is_owner:                                        # SEC-6
            self.storage.audit.add(AuditLog(actor=staff_id, action='conversation.view',
                                            target=conversation_id))
        return {
            'conversation': conversation,
            'messages': self.storage.messages.list(conversation.id, conversation.days),
            'events': self.storage.events.for_conversation(conversation.id, conversation.days),
            'suggestion': self.copilot.latest(conversation) if is_owner else None,
            'suggestion_pending_since': self.copilot.pending_since(conversation.id) if is_owner else None,
            'read_only': not is_owner,
        }

    # ---------- tiếp nhận / chỉ định / chuyển / đẩy cấp / đóng ----------

    def claim(self, staff_id, conversation_id):
        """BR-01: tiếp nhận có khoá – hai người bấm cùng lúc, đúng một người thành công."""

        self.permissions.require_role(staff_id, 'operator')
        self.permissions.require(staff_id, 'chat.claim')
        current = self.storage.conversations.get(conversation_id)
        ok, reason = self._can_take(staff_id, current.required_level.value)
        if not ok:
            raise OperatorError(f'Không thể tiếp nhận: {reason}')
        now = iso(utc_now())

        def change(conversation):
            if conversation.status != ConversationStatus.waiting:
                raise Rejected('Cuộc chat đã được tiếp nhận')
            return {'status': ConversationStatus.assigned, 'assignee_id': staff_id,
                    'assigned_at': now, 'pending_transfer': None}

        try:
            conversation = mutate(self.storage, conversation_id, change, attempts=1)
        except Rejected as error:
            raise OperatorError(str(error))
        except ConflictError as error:   # người khác vừa ghi xen giữa
            raise OperatorError('Cuộc chat đã được tiếp nhận') from error
        self._event(conversation_id, 'claimed', staff_id)
        staff = self.storage.staff.get(staff_id)
        self._message(conversation_id, SenderType.system,
                      CLAIMED_TEXT.format(name=self.display_name(staff)), kind='notice')
        self.schedule_copilot(conversation_id, staff_id)
        return conversation

    def assign(self, manager_id, conversation_id, staff_id, reason, override_level=False,
               required_level=None):
        """
        BR-03: quản lý chỉ định cuộc chat đang chờ HOẶC đang xử lý (thay người trực giữa chừng,
        vd người trước không đủ thẩm quyền). Người không đủ cấp phải override + lý do.
        required_level: nâng cấp cần thiết của cuộc chat (chỉ nâng, không hạ).
        """

        self.permissions.require_role(manager_id, 'manager')
        if not reason or not reason.strip():
            raise OperatorError('Cần ghi lý do chỉ định')
        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id == staff_id and current.status == ConversationStatus.assigned:
            raise OperatorError('Người này đang phụ trách cuộc chat rồi')
        order = ['none', 'C1', 'C2', 'C3']
        old_level = current.required_level.value
        new_level = required_level if required_level and order.index(required_level) > order.index(old_level) \
            else old_level
        ok, why = self._can_take(staff_id, new_level)
        if not ok and not (override_level and why.startswith('cấp')):
            raise OperatorError(f'Không thể chỉ định: {why}')
        now = iso(utc_now())

        def change(conversation):
            if conversation.status not in (ConversationStatus.waiting, ConversationStatus.assigned):
                raise Rejected('Chỉ chỉ định được cuộc chat đang chờ hoặc đang xử lý')
            return {'status': ConversationStatus.assigned, 'assignee_id': staff_id,
                    'assigned_at': now, 'pending_transfer': None, 'required_level': new_level}

        try:
            conversation = mutate(self.storage, conversation_id, change)
        except Rejected as error:
            raise OperatorError(str(error))
        self._event(conversation_id, 'assigned', manager_id,
                    {'to': staff_id, 'from': current.assignee_id, 'reason': reason,
                     'override_level': bool(override_level and not ok),
                     **({'from_level': old_level, 'to_level': new_level} if new_level != old_level else {})},
                    actor_type='manager')
        text = TAKEN_OVER_TEXT if current.status == ConversationStatus.assigned else CLAIMED_TEXT
        self._message(conversation_id, SenderType.system,
                      text.format(name=self.display_name(self.storage.staff.get(staff_id))), kind='notice')
        self.schedule_copilot(conversation_id, staff_id)
        return conversation

    def request_transfer(self, staff_id, conversation_id, to_staff_id, note=''):
        self.permissions.require(staff_id, 'chat.transfer')
        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới chuyển được')
        ok, why = self._can_take(to_staff_id, current.required_level.value)
        if not ok:
            raise OperatorError(f'Người nhận không phù hợp: {why}')
        offer = {'from': staff_id, 'to': to_staff_id, 'note': note, 'at': iso(utc_now())}
        conversation = mutate(self.storage, conversation_id, lambda c: {'pending_transfer': offer})
        self._event(conversation_id, 'transfer_requested', staff_id, offer)
        return conversation

    def respond_transfer(self, staff_id, conversation_id, accept):
        current = self.storage.conversations.get(conversation_id)
        offer = current.pending_transfer
        if not offer or offer.get('to') != staff_id:
            raise OperatorError('Không có đề nghị chuyển cho bạn')
        if accept:
            ok, why = self._can_take(staff_id, current.required_level.value)
            if not ok:
                raise OperatorError(f'Không thể nhận: {why}')
            now = iso(utc_now())

            def change(conversation):
                if conversation.pending_transfer != offer:
                    raise Rejected('Đề nghị chuyển đã thay đổi')
                return {'assignee_id': staff_id, 'assigned_at': now, 'pending_transfer': None,
                        'status': ConversationStatus.assigned}
            try:
                conversation = mutate(self.storage, conversation_id, change)
            except Rejected as error:
                raise OperatorError(str(error))
            self._event(conversation_id, 'transferred', staff_id, offer)
            self.schedule_copilot(conversation_id, staff_id)
            return conversation
        conversation = mutate(self.storage, conversation_id, lambda c: {'pending_transfer': None})
        self._event(conversation_id, 'transfer_declined', staff_id, offer)
        return conversation

    def escalate(self, staff_id, conversation_id, level, reason):
        """BR-04: đẩy lên cấp cao hơn cấp của người trực; cuộc chat quay lại hàng chờ."""

        self.permissions.require(staff_id, 'chat.escalate')
        _, eff = self._staff_view(staff_id)
        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới đẩy cấp được')
        if level not in ('C2', 'C3') or level_value(level) <= level_value(eff['level']):
            raise OperatorError(f'Cấp đẩy lên phải cao hơn cấp hiện tại ({eff["level"]})')
        if not reason or not reason.strip():
            raise OperatorError('Cần ghi lý do đẩy cấp')
        now = iso(utc_now())

        def change(conversation):
            required = level if level_value(level) > level_value(conversation.required_level.value) \
                else conversation.required_level.value
            return {'required_level': required, 'status': ConversationStatus.waiting,
                    'assignee_id': None, 'queued_at': now, 'sla_breached_at': None,
                    'pending_transfer': None}

        conversation = mutate(self.storage, conversation_id, change)
        self._event(conversation_id, 'escalated', staff_id,
                    {'from_level': current.required_level.value, 'to_level': level, 'reason': reason})
        self._message(conversation_id, SenderType.system, ESCALATED_TEXT, kind='notice')
        return conversation

    def close(self, staff_id, conversation_id):
        current = self.storage.conversations.get(conversation_id)
        staff = self.storage.staff.get(staff_id)
        if current.assignee_id != staff_id and 'manager' not in staff.roles:
            raise OperatorError('Chỉ người phụ trách hoặc quản lý mới đóng được')
        now = iso(utc_now())
        conversation = mutate(self.storage, conversation_id, lambda c: {
            'status': ConversationStatus.closed, 'closed_at': now, 'pending_transfer': None})
        self._event(conversation_id, 'closed', staff_id)
        self._message(conversation_id, SenderType.system, CLOSED_TEXT, kind='notice')
        return conversation

    def update_profile(self, staff_id, conversation_id, fields):
        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới sửa hồ sơ ca')
        fields = {k: v for k, v in fields.items() if k in current.profile.model_fields}

        def change(conversation):
            profile = conversation.profile.model_validate({**conversation.profile.model_dump(),
                                                           **fields})
            sources = {**conversation.profile_sources, **{k: 'staff' for k in fields}}
            return {'profile': profile, 'profile_sources': sources}

        conversation = mutate(self.storage, conversation_id, change)
        self._event(conversation_id, 'profile_edited', staff_id, {'fields': sorted(fields)})
        return conversation

    # ---------- gợi ý & gửi tin ----------

    def new_topic(self, staff_id, conversation_id):
        """Người trực đánh dấu: từ tin mới nhất của khách là vấn đề mới -> bỏ bệnh cũ, tạo lại gợi ý."""
        from backend.services.topic import start_new_topic

        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới đánh dấu được')
        messages = self.storage.messages.list(current.id, current.days)
        last = next((m for m in reversed(messages) if m.sender_type == SenderType.end_user), None)
        if last is None:
            raise OperatorError('Khách chưa nhắn tin nào')
        if start_new_topic(self.storage, conversation_id, last.id, 'staff', staff_id,
                           reason='người trực đánh dấu vấn đề mới') is None:
            raise OperatorError('Tin này đã là mốc chủ đề hiện tại')
        for old in self.storage.suggestions.for_conversation(current.id, current.days):
            if old.outcome is None and old.status == 'ready':
                old.outcome = 'superseded'
                self.storage.suggestions.update(old)
        self.schedule_copilot(conversation_id, staff_id,
                              then=lambda: self.case_memory.update(conversation_id))
        return self.storage.conversations.get(conversation_id)

    def regenerate(self, staff_id, conversation_id, instruction=None, background=True):
        current = self.storage.conversations.get(conversation_id)
        if current.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới tạo gợi ý')
        _, eff = self._staff_view(staff_id)
        if not eff['capabilities']['ai.use_copilot']:
            raise OperatorError('Không có quyền dùng gợi ý AI')
        if background:
            self.copilot.mark_pending(conversation_id)
            self.schedule(self.copilot.generate, conversation_id, staff_id, eff['level'], instruction)
            return None
        return self.copilot.generate(conversation_id, staff_id, eff['level'], instruction)

    def discard_suggestion(self, staff_id, suggestion_id):
        suggestion = self.storage.suggestions.get(suggestion_id)
        if suggestion.staff_id != staff_id:
            raise OperatorError('Gợi ý không thuộc về bạn')
        if suggestion.outcome is None:
            suggestion.outcome = 'discarded'
            self.storage.suggestions.update(suggestion)
        return suggestion

    def check(self, staff_id, conversation_id, text, suggestion_id=None):
        conversation = self.storage.conversations.get(conversation_id)
        if conversation.assignee_id != staff_id:
            raise OperatorError('Chỉ người phụ trách mới gửi tin')
        _, eff = self._staff_view(staff_id)
        messages = self.storage.messages.list(conversation.id, conversation.days)
        question = next((m.content for m in reversed(messages)
                         if m.sender_type == SenderType.end_user), '')
        if conversation.urgency == Urgency.emergency:
            question = '[KHÁCH CÓ DẤU HIỆU CẤP CỨU] ' + question
        typed = not suggestion_id
        settings = self.config.settings()
        use_llm = settings.get('guard_llm_enabled', False) and (
            not typed or settings.get('guard_llm_for_typed', True))
        return self.guard.check(conversation, staff_id, eff['level'], text.strip(), question,
                                use_llm=use_llm, typed=typed)

    def send(self, staff_id, conversation_id, text, suggestion_id=None, guard_check_id=None,
             confirm_reason=None):
        """Gửi tin cho khách: kiểm tra quyền, gợi ý, kết quả kiểm tra trước khi gửi."""

        text = (text or '').strip()
        if not text:
            raise OperatorError('Tin nhắn rỗng')
        conversation = self.storage.conversations.get(conversation_id)
        if conversation.assignee_id != staff_id or conversation.status != ConversationStatus.assigned:
            raise OperatorError('Bạn không phụ trách cuộc chat này')
        staff, eff = self._staff_view(staff_id)

        suggestion = self.storage.suggestions.get(suggestion_id) if suggestion_id else None
        send_mode = 'typed'
        if suggestion is not None:
            if suggestion.conversation_id != conversation_id or suggestion.staff_id != staff_id:
                raise OperatorError('Gợi ý không thuộc cuộc chat này')
            unchanged = text == suggestion.reply_draft.strip()
            if unchanged and not eff['capabilities']['ai.send_unedited']:
                raise OperatorError('Bạn cần chỉnh sửa gợi ý trước khi gửi (AC-2.9)')
            if (suggestion.scope_check or {}).get('status') == 'exceeds':
                level = (suggestion.scope_check or {}).get('suggested_level') or 'cấp cao hơn'
                raise OperatorError(f'Gợi ý vượt phạm vi cấp {eff["level"]}: không được gửi gợi ý này. '
                                    f'Hãy tự soạn câu trả lời, hoặc đẩy cấp lên {level}.')
            send_mode = 'ai_unedited' if unchanged else 'ai_edited'

        check = self.storage.guard_checks.get(guard_check_id) if guard_check_id else None
        if check is None or check.text != text or check.conversation_id != conversation_id:
            check = self.check(staff_id, conversation_id, text, suggestion.id if suggestion else None)
        if check.hard_block:
            raise OperatorError('Tin bị chặn: ' + '; '.join(self.guard.describe(check)))
        if self.guard.needs_confirmation(check):
            if not confirm_reason or not confirm_reason.strip():
                raise OperatorError('Cần xác nhận kèm lý do: ' +
                                    ('; '.join(self.guard.describe(check)) or check.explanation))
            check.confirmed_reason = confirm_reason.strip()
            self.storage.guard_checks.update(check)

        message = self._message(conversation_id, SenderType.staff, text, sender_id=staff_id,
                                sender_name=self.display_name(staff), send_mode=send_mode,
                                suggestion_id=suggestion.id if suggestion else None)
        if suggestion is not None:
            suggestion.outcome = 'sent_unedited' if send_mode == 'ai_unedited' else 'edited'
            suggestion.final_message_id = message.id
            suggestion.edit_ratio = round(1 - difflib.SequenceMatcher(
                None, suggestion.reply_draft, text).ratio(), 3)
            self.storage.suggestions.update(suggestion)
        return message, check

    # ---------- phía khách ở chế độ người trực ----------

    def customer_message(self, conversation_id, text):
        """
        Tin của khách khi cuộc chat ở chế độ người trực.
        BR-06: đã đóng <= 24h -> mở lại (người cũ nếu đang trực, không thì vào hàng chờ);
        > 24h -> tạo cuộc chat mới liên kết cuộc trước.

        Returns:
            tuple[conversation_id (có thể mới), Message]
        """

        conversation = self.storage.conversations.get(conversation_id)
        if conversation.status == ConversationStatus.closed:
            window = timedelta(hours=self.config.settings()['reopen_window_h'])
            if utc_now() - parse_iso(conversation.closed_at) > window:
                conversation = self._new_linked(conversation)
            else:
                self._reopen(conversation)
        message = self._message(conversation.id, SenderType.end_user, text,
                                sender_id=conversation.end_user_id)
        fresh = self.storage.conversations.get(conversation.id)
        # Gợi ý trước: người trực đang chờ nó; hồ sơ ca (AG-5) là việc nền, chạy sau.
        update_profile = lambda: self.case_memory.update(fresh.id)  # noqa: E731
        if fresh.status == ConversationStatus.assigned and fresh.assignee_id:
            self.schedule_copilot(fresh.id, fresh.assignee_id, then=update_profile)
        else:
            self.schedule(update_profile)
        return fresh.id, message

    def _reopen(self, conversation):
        previous = conversation.assignee_id
        back_to_previous = previous and self._can_take(previous, conversation.required_level.value)[0]
        now = iso(utc_now())
        mutate(self.storage, conversation.id, lambda c: {
            'status': ConversationStatus.assigned if back_to_previous else ConversationStatus.waiting,
            'assignee_id': previous if back_to_previous else None,
            'closed_at': None, 'queued_at': None if back_to_previous else now,
            'sla_breached_at': None})
        self._event(conversation.id, 'reopened', None,
                    {'assignee': previous if back_to_previous else None}, actor_type='end_user')

    def _new_linked(self, old):
        from backend.domain import Conversation
        new = Conversation(end_user_id=old.end_user_id, mode='human',
                           status=ConversationStatus.waiting, required_level=old.required_level,
                           profile=old.profile, profile_sources=old.profile_sources,
                           summary=old.summary, previous_conversation_id=old.id,
                           queued_at=iso(utc_now()))
        self.storage.conversations.add(new)
        self._event(new.id, 'created', old.end_user_id, {'previous': old.id}, actor_type='end_user')
        self._event(new.id, 'queued', None, {}, actor_type='system')
        return new

    # ---------- trạng thái trực & SLA ----------

    def set_presence(self, staff_id, status, force=False):
        """UI-2.9: rời ca khi còn cuộc chat -> phải chuyển; force=True trả về hàng chờ."""

        if status == 'online':
            self.permissions.require_role(staff_id, 'operator')
        active = self.mine(staff_id)['assigned']
        if status == 'offline' and active and not force:
            raise OperatorError(f'Bạn còn {len(active)} cuộc chat đang phụ trách. '
                                'Hãy chuyển cho người khác, hoặc xác nhận trả về hàng chờ.')
        self.permissions.set_presence(staff_id, status)
        if status == 'offline':
            now = iso(utc_now())
            for conversation in active:
                mutate(self.storage, conversation.id, lambda c: {
                    'status': ConversationStatus.waiting, 'assignee_id': None, 'queued_at': now})
                self._event(conversation.id, 'returned_to_queue', staff_id, {'reason': 'offline'})
                self._message(conversation.id, SenderType.system, RETURNED_TEXT, kind='notice')

    def check_sla(self, now=None):
        """BR-05: đánh dấu cuộc chat chờ quá SLA (một lần) – quản lý được cảnh báo ở P3."""

        now = now or utc_now()
        settings = self.config.settings()
        breached = []
        for conversation in self.storage.conversations.find(status='waiting'):
            if conversation.sla_breached_at:
                continue
            limit = settings['sla_emergency_s'] if conversation.urgency == Urgency.emergency \
                else settings['sla_normal_s']
            started = parse_iso(conversation.queued_at or conversation.created_at)
            if (now - started).total_seconds() > limit:
                stamp = iso(now)
                mutate(self.storage, conversation.id,
                       lambda c: None if c.sla_breached_at else {'sla_breached_at': stamp})
                self._event(conversation.id, 'sla_breached', None,
                            {'waited_s': int((now - started).total_seconds()), 'limit_s': limit},
                            actor_type='system')
                breached.append(conversation.id)
        return breached


class SlaMonitor:
    """Luồng nền kiểm tra SLA định kỳ."""

    def __init__(self, operator, interval_s=30):
        self.operator = operator
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name='sla-monitor')

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self.interval_s):
            try:
                self.operator.check_sla()
            except Exception:   # không để lỗi làm dừng giám sát
                import logging
                logging.getLogger('backend').exception('Lỗi kiểm tra SLA')
