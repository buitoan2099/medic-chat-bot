"""
Agent quản lý AG-7 (đặc tả 03 mục 7, BR-10…BR-12, D-6).

- Chỉ đọc dữ liệu qua công cụ; thao tác ghi = tạo ĐỀ XUẤT, chỉ thực hiện khi quản lý
  bấm Xác nhận.
- Form có số liệu do code dựng (BR-11) và hiển thị thành thẻ; AG-7 viết phần nhận định.
- Báo cáo nhanh (không cần LLM) dùng cùng hàm dựng form.
"""

import json
from datetime import timedelta

from backend.agents.registry import AG7_MANAGER
from backend.core import LOCAL_TZ, iso, parse_iso, utc_now
from backend.domain import ActionProposal, AiRun, AuditLog, ManagerMessage, ManagerSession
from backend.llm.gateway import PRIORITY_MANAGER, LLMError
from backend.services import forms
from backend.services.metrics import MetricsService, days_between, today
from backend.services.operator_service import OperatorError
from backend.services.permissions import CAPABILITY_DEFAULTS, LEVELS, PermissionError_
from rag import rag
from rag.pdf_parser import fold

MAX_TOOL_ROUNDS = 5
HISTORY_MESSAGES = 10
UNAVAILABLE = ('AG-7 hiện không khả dụng (mô hình không kết nối được). Bạn vẫn dùng được các nút '
               'báo cáo nhanh và popup "Điều chỉnh nhanh".')


class ManagerError(RuntimeError):
    pass


def _period(args):
    """Khoảng ngày; mặc định hôm nay (giờ VN) – BR-12/prompt AG-7."""
    start = args.get('from_day') or today()
    end = args.get('to_day') or start
    days_between(start, end)          # kiểm tra hợp lệ
    return start, end


def _tool(name, description, properties, required=()):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties, 'required': list(required)}}}


DAY = {'type': 'string', 'description': 'YYYY-MM-DD (giờ Việt Nam)'}
TOOLS = [
    _tool('list_staff', 'Danh sách nhân sự: cấp, vai trò, trạng thái trực, hạn chứng chỉ.',
          {'query': {'type': 'string', 'description': 'tên/tên đăng nhập (tuỳ chọn)'}}),
    _tool('find_conversations', 'Tìm cuộc chat theo người dùng, người trực, trạng thái, khoảng ngày.',
          {'user': {'type': 'string'}, 'staff': {'type': 'string'},
           'status': {'type': 'string', 'enum': ['ai_active', 'waiting', 'assigned', 'closed']},
           'from_day': DAY, 'to_day': DAY, 'sla_breached': {'type': 'boolean'}}),
    _tool('get_conversation', 'Chi tiết + form F-1 tóm tắt một cuộc chat (mã đầy đủ hoặc 6 ký tự cuối).',
          {'conversation': {'type': 'string'}}, ['conversation']),
    _tool('get_operator_workday', 'Form F-6 NỘI DUNG người trực đã xử lý (từng cuộc chat: khách hỏi gì, '
          'đã trả lời gì, kết quả). Dùng khi hỏi "hôm nay X xử lý những gì / tư vấn gì".',
          {'staff': {'type': 'string'}, 'from_day': DAY, 'to_day': DAY}, ['staff']),
    _tool('get_operator_metrics', 'Form F-2 hiệu suất một người trực trong khoảng ngày.',
          {'staff': {'type': 'string'}, 'from_day': DAY, 'to_day': DAY}, ['staff']),
    _tool('compare_operators', 'Form F-5 so sánh người trực (bỏ trống staff = tất cả).',
          {'staff': {'type': 'array', 'items': {'type': 'string'}}, 'from_day': DAY, 'to_day': DAY}),
    _tool('get_operations_overview', 'Form F-4 báo cáo vận hành theo khoảng ngày.',
          {'from_day': DAY, 'to_day': DAY}),
    _tool('evaluate_conversation_quality', 'Dữ liệu + khung form F-3 để chấm chất lượng một cuộc chat.',
          {'conversation': {'type': 'string'}}, ['conversation']),
    _tool('get_permission_history', 'Lịch sử cấp/thu hồi quyền của một nhân sự.',
          {'staff': {'type': 'string'}}, ['staff']),
    _tool('search_documents', 'Tra tài liệu (RAG); trả đoạn + trang để trích dẫn.',
          {'query': {'type': 'string'}}, ['query']),
    _tool('propose_permission_change', 'ĐỀ XUẤT đổi cấp/quyền (chỉ thực hiện khi quản lý xác nhận).',
          {'staff': {'type': 'string'}, 'key': {'type': 'string',
                                                'description': 'level hoặc ' + ', '.join(CAPABILITY_DEFAULTS)},
           'value': {'description': 'C1/C2/C3, true/false hoặc số'},
           'reason': {'type': 'string'}, 'effective_from': DAY, 'effective_to': DAY},
          ['staff', 'key', 'value', 'reason']),
    _tool('propose_assignment', 'ĐỀ XUẤT giao một cuộc chat cho người trực (chỉ thực hiện khi xác nhận).',
          {'conversation': {'type': 'string'}, 'staff': {'type': 'string'}, 'reason': {'type': 'string'},
           'override_level': {'type': 'boolean'}},
          ['conversation', 'staff', 'reason']),
]


class ManagerAgentService:
    def __init__(self, storage, gateway, config_service, permissions, operator, index_manager):
        self.storage = storage
        self.gateway = gateway
        self.config = config_service
        self.permissions = permissions
        self.operator = operator
        self.index = index_manager
        self.metrics = MetricsService(storage)

    # ============================================================
    # Tra cứu đối tượng (hỏi lại khi mơ hồ – prompt AG-7 mục 6)
    # ============================================================

    def _staff_name(self, staff):
        return f'{staff.title} {staff.display_name}'.strip()

    def resolve_staff(self, query):
        members = self.storage.staff.all()
        exact = [s for s in members if query in (s.id, s.username)]
        if exact:
            return exact[0]
        key = fold(query)

        def matches(staff):
            name, full = fold(staff.display_name), fold(f'{staff.title} {staff.display_name}')
            # Chấp nhận cả tên kèm chức danh ("Dược sĩ Nguyễn Lan") và một phần tên ("Lan")
            return key and (key in name or key in full or name in key or key == fold(staff.username))

        found = [s for s in members if matches(s)]
        if len(found) == 1:
            return found[0]
        if not found:
            raise ManagerError(f'Không tìm thấy nhân sự "{query}"')
        raise ManagerError('AMBIGUOUS: ' + json.dumps(
            [{'id': s.id, 'name': self._staff_name(s), 'username': s.username} for s in found],
            ensure_ascii=False))

    def resolve_conversation(self, query):
        query = query.strip().lstrip('#')
        try:
            return self.storage.conversations.get(query)
        except KeyError:
            pass
        found = [c for c in self.storage.conversations.find() if c.id.upper().endswith(query.upper())]
        if len(found) == 1:
            return found[0]
        if not found:
            raise ManagerError(f'Không tìm thấy cuộc chat "{query}"')
        raise ManagerError('AMBIGUOUS: ' + json.dumps([c.id for c in found]))

    def _user_label(self, conversation):
        try:
            user = self.storage.end_users.get(conversation.end_user_id)
            return user.display_name or f'Khách {conversation.end_user_id[-6:]}'
        except KeyError:
            return f'Khách {conversation.end_user_id[-6:]}'

    # ============================================================
    # Dữ liệu cho form F-1 / F-3
    # ============================================================

    def conversation_facts(self, conversation, transcript_limit=40):
        messages = self.storage.messages.list(conversation.id, conversation.days)
        events = self.storage.events.for_conversation(conversation.id, conversation.days)
        staff_ids = {m.sender_id for m in messages if m.sender_type == 'staff'} | (
            {conversation.assignee_id} if conversation.assignee_id else set())
        names = []
        for staff_id in staff_ids:
            try:
                staff = self.storage.staff.get(staff_id)
                names.append(f'{self._staff_name(staff)} ({self.permissions.effective(staff_id)["level"]})')
            except KeyError:
                continue
        to_human = next((e for e in events if e.type == 'mode_changed'), None)
        local = lambda t: parse_iso(t).astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')  # noqa: E731
        moves = [f'{e.type} {local(e.created_at)}' + (f' ({e.data.get("reason")})' if e.data.get('reason') else '')
                 for e in events if e.type in ('transferred', 'escalated', 'assigned', 'returned_to_queue')]
        checks = [c for day in conversation.days for c in self.storage.guard_checks.by_day(day)
                  if c.conversation_id == conversation.id]
        alerts = []
        blocked = [c for c in checks if c.verdict == 'block']
        if blocked:
            alerts.append(f'{len(blocked)} cảnh báo vượt quyền '
                          f'({sum(1 for c in blocked if c.confirmed_reason)} gửi sau xác nhận)')
        if any(c.hard_block for c in checks):
            alerts.append('có tin bị chặn cứng')
        if conversation.urgency.value == 'emergency':
            alerts.append('có dấu hiệu cấp cứu')
        if conversation.sla_breached_at:
            alerts.append('đã chờ quá SLA')
        profile = '; '.join(f'{k}: {v}' for k, v in conversation.profile.model_dump().items()
                            if v and k != 'needs_confirmation')
        counts = {k: sum(1 for m in messages if m.sender_type == k) for k in ('end_user', 'ai', 'staff')}
        last = messages[-1].created_at if messages else None
        facts = {
            'id': conversation.id, 'code': conversation.id[-6:], 'user': self._user_label(conversation),
            'staff': ', '.join(names), 'start': local(conversation.created_at),
            'end': local(conversation.closed_at) if conversation.closed_at else (local(last) + ' (đang mở)' if last else None),
            'channel': (f'AI → người trực lúc {local(to_human.created_at)}' if to_human
                        else ('chỉ AI' if conversation.mode == 'ai' else 'chỉ người trực')),
            'required_level': conversation.required_level.value, 'urgency': conversation.urgency.value,
            'profile': profile, 'summary': conversation.summary, 'counts': counts,
            'moves': '; '.join(moves), 'status': conversation.status.value, 'alerts': '; '.join(alerts),
        }
        label = {'end_user': 'Khách', 'ai': 'AI', 'system': 'Hệ thống'}
        transcript = [f'[{m.sender_name or label.get(m.sender_type, "Người trực")} {local(m.created_at)}] {m.content[:400]}'
                      for m in messages[-transcript_limit:]]
        return facts, transcript

    # ============================================================
    # Công cụ (BR-10: chỉ đọc + đề xuất)
    # ============================================================

    def run_tool(self, name, args, ctx):
        """Thực thi một công cụ. Trả (dữ liệu cho LLM, thẻ hiển thị | None)."""

        handler = getattr(self, f'_tool_{name}', None)
        if handler is None:
            return {'error': f'Không có công cụ {name}'}, None
        try:
            return handler(args or {}, ctx)
        except ManagerError as error:
            text = str(error)
            if text.startswith('AMBIGUOUS: '):
                return {'ambiguous': json.loads(text[11:]),
                        'instruction': 'Có nhiều đối tượng trùng: hỏi lại quản lý, liệt kê lựa chọn.'}, None
            return {'error': text}, None
        except (ValueError, KeyError, PermissionError_, OperatorError) as error:
            return {'error': str(error)}, None

    def _tool_list_staff(self, args, ctx):
        warn_days = self.config.settings()['credential_expiry_warning_days']
        horizon = (utc_now() + timedelta(days=warn_days)).astimezone(LOCAL_TZ).strftime('%Y-%m-%d')
        presence = self.storage.presence.current()
        key = fold(args.get('query') or '')
        rows = []
        for staff in self.storage.staff.all():
            if key and key not in fold(staff.display_name) and key != fold(staff.username):
                continue
            eff = self.permissions.effective(staff.id)
            cred = staff.credential
            rows.append({'id': staff.id, 'name': self._staff_name(staff), 'username': staff.username,
                         'level': eff['level'], 'roles': staff.roles, 'active': staff.active,
                         'presence': presence[staff.id].status if staff.id in presence else 'offline',
                         'credential': cred.kind if cred else None,
                         'credential_expires': cred.expires_at if cred else None,
                         'credential_expiring_soon': bool(cred and cred.expires_at and cred.expires_at <= horizon)})
        return {'staff': rows}, None

    def _tool_find_conversations(self, args, ctx):
        conversations = self.storage.conversations.find(status=args.get('status'))
        if args.get('from_day') or args.get('to_day'):
            days = set(days_between(*_period(args)))
            conversations = [c for c in conversations if days & set(c.days)]
        if args.get('staff'):
            staff = self.resolve_staff(args['staff'])
            conversations = [c for c in conversations if c.assignee_id == staff.id or any(
                m.sender_id == staff.id for m in self.storage.messages.list(c.id, c.days))]
        if args.get('user'):
            key = fold(args['user'])
            conversations = [c for c in conversations
                             if key in fold(self._user_label(c)) or c.id.upper().endswith(args['user'].upper())]
        if args.get('sla_breached'):
            conversations = [c for c in conversations if c.sla_breached_at]
        rows = [{'id': c.id, 'code': c.id[-6:], 'user': self._user_label(c), 'status': c.status.value,
                 'required_level': c.required_level.value, 'urgency': c.urgency.value,
                 'assignee_id': c.assignee_id, 'created_at': c.created_at,
                 'sla_breached': bool(c.sla_breached_at)} for c in conversations[-30:]]
        card = {'type': 'table', 'title': f'Cuộc chat tìm được ({len(conversations)})', 'rows': rows}
        return {'count': len(conversations), 'conversations': rows}, card

    def _tool_get_conversation(self, args, ctx):
        conversation = self.resolve_conversation(args['conversation'])
        facts, transcript = self.conversation_facts(conversation)
        card = {'type': 'form', 'form': 'F-1', 'markdown': forms.conversation_summary(facts),
                'conversation_id': conversation.id}
        return {'facts': facts, 'transcript': transcript}, card

    def _name_of(self, staff_id):
        try:
            return self._staff_name(self.storage.staff.get(staff_id))
        except (KeyError, TypeError):
            return 'người khác'

    def workday_facts(self, staff, start, end, reply_limit=3):
        """Các cuộc chat người trực đã xử lý trong [start, end]: tiếp nhận / được giao / có gửi tin."""

        days = set(days_between(start, end))
        local = lambda t: parse_iso(t).astimezone(LOCAL_TZ)  # noqa: E731
        in_period = lambda t: local(t).strftime('%Y-%m-%d') in days  # noqa: E731
        rows, transcripts = [], {}
        for conversation in self.storage.conversations.find():
            if not days & set(conversation.days):
                continue
            messages = self.storage.messages.list(conversation.id, conversation.days)
            events = self.storage.events.for_conversation(conversation.id, conversation.days)
            mine = [m for m in messages if m.sender_type == 'staff' and m.sender_id == staff.id
                    and in_period(m.created_at)]
            took = [e for e in events if in_period(e.created_at) and (
                (e.type == 'claimed' and e.actor_id == staff.id)
                or (e.type in ('assigned', 'transferred') and (e.data or {}).get('to') == staff.id))]
            if not mine and not took and conversation.assignee_id != staff.id:
                continue
            if not mine and not took and not in_period(conversation.created_at):
                continue
            start_at = min([e.created_at for e in took] + [m.created_at for m in mine])  \
                if (took or mine) else conversation.created_at
            last_at = max(m.created_at for m in mine) if mine else None
            customer = [m.content for m in messages if m.sender_type == 'end_user']
            issue = conversation.profile.chief_complaint or (customer[0][:160] if customer else '')
            modes = [m.send_mode or 'typed' for m in mine]
            ai_usage = ', '.join(f'{label} {modes.count(k)}' for k, label in
                                 (('ai_unedited', 'gửi nguyên văn'), ('ai_edited', 'sửa rồi gửi'))
                                 if modes.count(k))
            moves = []
            for e in events:
                data, at = e.data or {}, local(e.created_at).strftime('%H:%M')
                if e.type == 'transferred' and data.get('from') == staff.id:
                    moves.append(f'chuyển cho {self._name_of(data.get("to"))} {at}')
                elif e.type == 'transferred' and data.get('to') == staff.id:
                    moves.append(f'nhận chuyển từ {self._name_of(data.get("from"))} {at}')
                elif e.type == 'escalated' and e.actor_id == staff.id:
                    moves.append(f'đẩy cấp lên {data.get("to_level", "?")} {at}'
                                 + (f' ({data["reason"]})' if data.get('reason') else ''))
                elif e.type == 'returned_to_queue' and e.actor_id == staff.id:
                    moves.append(f'trả về hàng chờ {at}')
            checks = [c for day in conversation.days for c in self.storage.guard_checks.by_day(day)
                      if c.conversation_id == conversation.id and c.staff_id == staff.id]
            alerts = []
            warned = [c for c in checks if c.verdict in ('warn', 'block') and not c.hard_block]
            if warned:
                alerts.append(f'{len(warned)} cảnh báo khi gửi')
            if any(c.hard_block for c in checks):
                alerts.append('có tin bị chặn')
            if conversation.sla_breached_at:
                alerts.append('khách chờ quá SLA')
            first, last = local(start_at).strftime('%H:%M'), local(last_at).strftime('%H:%M') if last_at else None
            time = first + (f'–{last}' if last and last != first else '')
            if len(days) > 1:
                time = local(start_at).strftime('%d/%m ') + time
            rows.append({'id': conversation.id, 'code': conversation.id[-6:], 'time': time,
                         'sort': start_at, 'user': self._user_label(conversation),
                         'required_level': conversation.required_level.value,
                         'urgency': conversation.urgency.value, 'status': conversation.status.value,
                         'issue': issue, 'summary': conversation.summary,
                         'staff_messages': len(mine),
                         'replies': [m.content[:160].replace('\n', ' ') for m in mine[-reply_limit:]],
                         'ai_usage': ai_usage, 'moves': '; '.join(moves), 'alerts': '; '.join(alerts)})
            label = {'end_user': 'Khách', 'ai': 'AI', 'system': 'Hệ thống'}
            transcripts[conversation.id[-6:]] = [
                f'[{m.sender_name or label.get(m.sender_type, "Người trực")}] {m.content[:200]}'
                for m in messages[-10:] if m.sender_type != 'system']
        rows.sort(key=lambda r: r['sort'])
        return rows, transcripts

    def _tool_get_operator_workday(self, args, ctx):
        staff = self.resolve_staff(args['staff'])
        start, end = _period(args)
        rows, transcripts = self.workday_facts(staff, start, end)
        level = self.permissions.effective(staff.id)['level']
        card = {'type': 'form', 'form': 'F-6', 'staff_id': staff.id,
                'markdown': forms.operator_workday(self._staff_name(staff), level, start, end, rows)}
        # Giới hạn ngữ cảnh cho LLM: 12 cuộc gần nhất, mỗi cuộc 10 tin
        recent = rows[-12:]
        return {'staff': self._staff_name(staff), 'level': level, 'from_day': start, 'to_day': end,
                'conversations': [{k: v for k, v in r.items() if k != 'sort'} for r in recent],
                'transcripts': {r['code']: transcripts[r['code']] for r in recent},
                'instruction': ('Thẻ F-6 đã hiển thị danh sách. KHÔNG liệt kê lại từng cuộc. Chỉ viết '
                                'nhận định ngắn: các nhóm vấn đề khách hỏi nhiều, cách trả lời có phù hợp '
                                'phạm vi cấp không, ca cần quản lý xem lại (nêu mã), đề xuất.')}, card

    def _tool_get_operator_metrics(self, args, ctx):
        staff = self.resolve_staff(args['staff'])
        start, end = _period(args)
        metrics = self.metrics.operator(staff.id, start, end)
        level = self.permissions.effective(staff.id)['level']
        card = {'type': 'form', 'form': 'F-2', 'staff_id': staff.id,
                'markdown': forms.operator_performance(self._staff_name(staff), level, metrics)}
        return {'staff': self._staff_name(staff), 'level': level, 'metrics': metrics}, card

    def _tool_compare_operators(self, args, ctx):
        start, end = _period(args)
        names = args.get('staff') or []
        members = [self.resolve_staff(n) for n in names] if names else [
            s for s in self.storage.staff.all() if 'operator' in s.roles and s.active]
        metrics = self.metrics.compare([s.id for s in members], start, end)
        rows = [(self._staff_name(s), self.permissions.effective(s.id)['level'], m)
                for s, m in zip(members, metrics)]
        card = {'type': 'form', 'form': 'F-5', 'markdown': forms.compare(rows, start, end)}
        return {'rows': [{'name': n, 'level': lv, 'metrics': m} for n, lv, m in rows]}, card

    def _tool_get_operations_overview(self, args, ctx):
        start, end = _period(args)
        overview = self.metrics.overview(start, end)
        return {'overview': overview}, {'type': 'form', 'form': 'F-4', 'markdown': forms.operations(overview)}

    def _tool_evaluate_conversation_quality(self, args, ctx):
        conversation = self.resolve_conversation(args['conversation'])
        facts, transcript = self.conversation_facts(conversation, transcript_limit=60)
        card = {'type': 'form', 'form': 'F-3', 'markdown': forms.quality(facts, narrative='(xem phần đánh giá bên dưới)'),
                'conversation_id': conversation.id}
        return {'facts': facts, 'transcript': transcript,
                'instruction': 'Chấm điểm 1–5 từng tiêu chí F-3, mỗi điểm kèm bằng chứng trích tin.'}, card

    def _tool_get_permission_history(self, args, ctx):
        staff = self.resolve_staff(args['staff'])
        grants = [g.model_dump(mode='json') for g in self.storage.permissions.for_staff(staff.id)]
        return {'staff': self._staff_name(staff), 'effective': self.permissions.effective(staff.id),
                'credential': staff.credential.model_dump() if staff.credential else None,
                'grants': grants}, None

    def _tool_search_documents(self, args, ctx):
        settings = self.config.settings()
        collection = settings['active_collection']
        result = rag.retrieve(args['query'], k=5, client=self.index.client,
                              bm25_weights=self.config.bm25_weights(),
                              use_dense=self.index.has_vectors(collection), collection=collection,
                              min_score=None)
        blocks = rag.build_context_blocks(result['results'], collection, max_chars=6000)
        return {'results': [{'title': ' › '.join(b['metadata'].get('path') or []),
                             'source_file': b['metadata'].get('source_file'),
                             'page': b['page_start'], 'page_end': b['page_end'],
                             'text': b['text'][:1500]} for b in blocks]}, None

    def _tool_propose_permission_change(self, args, ctx):
        staff = self.resolve_staff(args['staff'])
        key, value, reason = args['key'], args['value'], (args.get('reason') or '').strip()
        if not reason:
            return {'error': 'Cần lý do cho đề xuất'}, None
        if isinstance(value, str) and value.lower() in ('true', 'false'):
            value = value.lower() == 'true'
        if key == 'level':
            if value not in LEVELS:
                return {'error': f'Cấp không hợp lệ: {value}'}, None
            from backend.services.permissions import level_value, max_level_allowed
            allowed = max_level_allowed(staff)
            if level_value(value) > level_value(allowed):          # AC-3.3
                return {'error': f'Không thể đề xuất {value} cho {self._staff_name(staff)}: chứng chỉ '
                                 f'chỉ cho phép {allowed} (chưa xác minh hoặc hết hạn). Hướng dẫn quản lý '
                                 'xác minh chứng chỉ trên trang Phân quyền trước.'}, None
        elif key not in CAPABILITY_DEFAULTS:
            return {'error': f'Quyền không tồn tại: {key}'}, None
        before = self.permissions.effective(staff.id)
        current = before['level'] if key == 'level' else before['capabilities'][key]
        payload = {'staff_id': staff.id, 'key': key, 'value': value,
                   'effective_from': self._day_start(args.get('effective_from')),
                   'effective_to': self._day_start(args.get('effective_to'))}
        proposal = self.storage.manager.add_proposal(ActionProposal(
            session_id=ctx.get('session_id'), manager_id=ctx['manager_id'], kind='permission',
            payload=payload, before={key: current}, reason=reason,
            summary=f'{self._staff_name(staff)}: {key} {current} → {value}'
                    + (f' từ {args["effective_from"]}' if args.get('effective_from') else '')
                    + (f' đến {args["effective_to"]}' if args.get('effective_to') else '')))
        return {'proposal_id': proposal.id, 'status': 'pending',
                'note': 'Chưa có hiệu lực cho tới khi quản lý bấm Xác nhận.'}, \
            {'type': 'proposal', 'proposal': proposal.model_dump(mode='json')}

    def _tool_propose_assignment(self, args, ctx):
        conversation = self.resolve_conversation(args['conversation'])
        staff = self.resolve_staff(args['staff'])
        reason = (args.get('reason') or '').strip()
        if not reason:
            return {'error': 'Cần lý do cho đề xuất'}, None
        ok, why = self.operator._can_take(staff.id, conversation.required_level.value)
        override = bool(args.get('override_level'))
        if not ok and not (override and why.startswith('cấp')):
            return {'error': f'Không thể giao cho {self._staff_name(staff)}: {why}'}, None
        proposal = self.storage.manager.add_proposal(ActionProposal(
            session_id=ctx.get('session_id'), manager_id=ctx['manager_id'], kind='assignment',
            payload={'conversation_id': conversation.id, 'staff_id': staff.id, 'override_level': override},
            before={'assignee_id': conversation.assignee_id, 'status': conversation.status.value},
            reason=reason, summary=f'Giao cuộc chat #{conversation.id[-6:]} cho {self._staff_name(staff)}'
                                   + (' (vượt cấp, đã ghi lý do)' if not ok else '')))
        return {'proposal_id': proposal.id, 'status': 'pending',
                'note': 'Chưa có hiệu lực cho tới khi quản lý bấm Xác nhận.'}, \
            {'type': 'proposal', 'proposal': proposal.model_dump(mode='json')}

    @staticmethod
    def _day_start(day):
        if not day:
            return None
        return iso(parse_iso(f'{day}T00:00:00+07:00'))

    # ============================================================
    # Xác nhận / huỷ đề xuất (D-6)
    # ============================================================

    def decide(self, manager_id, proposal_id, confirm, edits=None):
        self.permissions.require_role(manager_id, 'manager')
        proposal = self.storage.manager.get_proposal(proposal_id)
        if proposal.manager_id != manager_id:
            raise PermissionError_('Đề xuất thuộc quản lý khác')
        if proposal.status != 'pending':
            raise ManagerError(f'Đề xuất đã {proposal.status}')
        proposal.decided_at = iso(utc_now())
        if not confirm:
            proposal.status = 'cancelled'
            self.storage.manager.update_proposal(proposal)
            return proposal
        payload = {**proposal.payload, **(edits or {})}
        try:
            if proposal.kind == 'permission':
                self.permissions.grant(payload['staff_id'], payload['key'], payload['value'], manager_id,
                                       proposal.reason, payload.get('effective_from'),
                                       payload.get('effective_to'), source='agent_proposal')
            else:
                self.operator.assign(manager_id, payload['conversation_id'], payload['staff_id'],
                                     proposal.reason, payload.get('override_level', False))
            proposal.status, proposal.result = 'confirmed', 'Đã thực hiện'
        except (PermissionError_, OperatorError, ValueError) as error:
            proposal.status, proposal.result = 'failed', str(error)
        proposal.payload = payload
        self.storage.manager.update_proposal(proposal)
        self.storage.audit.add(AuditLog(actor=manager_id, action=f'proposal.{proposal.status}',
                                        target=proposal.id, data={'kind': proposal.kind, 'payload': payload}))
        return proposal

    # ============================================================
    # Phiên chat với AG-7
    # ============================================================

    def new_session(self, manager_id, title='Phiên làm việc'):
        self.permissions.require_role(manager_id, 'manager')
        return self.storage.manager.add_session(ManagerSession(manager_id=manager_id, title=title))

    def session(self, manager_id, session_id):
        session = self.storage.manager.get_session(session_id)
        if session.manager_id != manager_id:
            raise PermissionError_('Phiên thuộc quản lý khác')
        return session

    def _history(self, session):
        """Lịch sử phiên cho LLM (BR-12): lời quản lý + câu trả lời + ghi chú thẻ đã hiển thị."""
        messages = []
        for message in self.storage.manager.messages(session)[-HISTORY_MESSAGES:]:
            content = message.content
            notes = [f'[đã hiển thị {c.get("form") or c["type"]}' + (f' {c.get("title", "")}' if c.get('title') else '') + ']'
                     for c in message.cards]
            if notes:
                content = (content + '\n' if content else '') + ' '.join(notes)
            messages.append({'role': message.role, 'content': content or '(trống)'})
        return messages

    def ask(self, manager_id, session_id, text):
        """Một lượt hỏi AG-7. Trả về ManagerMessage của trợ lý (kèm thẻ)."""

        self.permissions.require_role(manager_id, 'manager')
        session = self.session(manager_id, session_id)
        history = self._history(session)
        self.storage.manager.add_message(ManagerMessage(session_id=session.id, role='user', content=text))

        cfg = self.config.agent(AG7_MANAGER)
        prompt, version = self.config.prompt(AG7_MANAGER)
        now_local = utc_now().astimezone(LOCAL_TZ)
        messages = [{'role': 'system', 'content': f'{prompt}\n\nNGÀY HÔM NAY: {now_local:%Y-%m-%d} '
                                                  f'(giờ Việt Nam, {now_local:%H:%M})'}]
        messages += history + [{'role': 'user', 'content': text}]
        ctx = {'manager_id': manager_id, 'session_id': session.id}
        cards, content = [], ''
        run = AiRun(agent_id=AG7_MANAGER, prompt_version=version, provider=cfg.provider, model=cfg.model)
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                result = self.gateway.chat_tools(cfg, messages, PRIORITY_MANAGER, TOOLS)
                run.provider, run.model = result['provider'], result['model']
                if not result['tool_calls']:
                    content = result['content']
                    break
                messages.append({'role': 'assistant', 'content': result['content'] or '',
                                 'tool_calls': [{'function': {'name': c['name'], 'arguments': c['arguments']}}
                                                for c in result['tool_calls']]})
                shown_forms = []
                for call in result['tool_calls']:
                    data, card = self.run_tool(call['name'], call['arguments'], ctx)
                    if card:
                        cards.append(card)
                        if card['type'] == 'form':
                            shown_forms.append(card['form'])
                    messages.append({'role': 'tool', 'tool_name': call['name'],
                                     'content': json.dumps(data, ensure_ascii=False, default=str)[:12000]})
                if shown_forms:
                    # Đo thật: qwen3 vẫn chép lại bảng số liệu dù prompt đã dặn -> nhắc ngay
                    # trước lượt viết câu trả lời (BR-11: số liệu chỉ hiển thị qua thẻ do code dựng).
                    messages.append({'role': 'user', 'content': (
                        f'[Hệ thống] Thẻ {", ".join(shown_forms)} với đầy đủ số liệu ĐÃ hiển thị cho '
                        'quản lý. Chỉ viết phần NHẬN ĐỊNH: tối đa 5 gạch đầu dòng, mỗi ý kèm bằng chứng '
                        'ngắn. KHÔNG lặp lại bảng, KHÔNG chép lại con số.')})
            else:
                content = 'Yêu cầu cần quá nhiều bước tra cứu; bạn hãy hỏi cụ thể hơn.'
        except LLMError as error:
            run.status, run.error = 'error', str(error)[:500]
            content = UNAVAILABLE
        self.storage.ai_runs.add(run)
        reply = ManagerMessage(session_id=session.id, role='assistant', content=content, cards=cards)
        return self.storage.manager.add_message(reply)

    # ============================================================
    # Báo cáo nhanh – không cần LLM (UI-3.4)
    # ============================================================

    QUICK = {
        'today': ('Báo cáo hôm nay', 'get_operations_overview', lambda a: {}),
        'week': ('Báo cáo 7 ngày', 'get_operations_overview',
                 lambda a: {'from_day': (utc_now() - timedelta(days=6)).astimezone(LOCAL_TZ).strftime('%Y-%m-%d'),
                            'to_day': today()}),
        'compare_today': ('So sánh người trực hôm nay', 'compare_operators', lambda a: {}),
        'sla': ('Cuộc chat đang chờ quá SLA', 'find_conversations',
                lambda a: {'status': 'waiting', 'sla_breached': True}),
        'waiting': ('Cuộc chat đang chờ', 'find_conversations', lambda a: {'status': 'waiting'}),
        'operator': ('Hiệu suất người trực', 'get_operator_metrics', lambda a: a),
        'workday': ('Nội dung người trực đã xử lý', 'get_operator_workday', lambda a: a),
        'conversation': ('Tóm tắt cuộc chat', 'get_conversation', lambda a: a),
    }

    def quick(self, manager_id, session_id, action, args=None):
        self.permissions.require_role(manager_id, 'manager')
        session = self.session(manager_id, session_id)
        if action not in self.QUICK:
            raise ManagerError(f'Không có báo cáo nhanh "{action}"')
        title, tool, build = self.QUICK[action]
        self.storage.manager.add_message(ManagerMessage(session_id=session.id, role='user',
                                                        content=f'[Báo cáo nhanh] {title}'))
        data, card = self.run_tool(tool, build(args or {}), {'manager_id': manager_id,
                                                             'session_id': session.id})
        content = data.get('error') or ('' if card else json.dumps(data, ensure_ascii=False)[:2000])
        return self.storage.manager.add_message(ManagerMessage(
            session_id=session.id, role='assistant', content=content, cards=[card] if card else []))
