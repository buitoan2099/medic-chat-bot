"""
Chỉ số hiệu suất & vận hành (đặc tả 01 mục 4). BR-11: mọi con số do code tính từ
dữ liệu sự kiện / tin nhắn; agent quản lý chỉ diễn giải.

Khoảng thời gian tính theo NGÀY giờ Việt Nam [from_day, to_day] (bao gồm cả hai đầu).
"""

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from backend.core import local_date, parse_iso, utc_now


def days_between(from_day, to_day):
    start, end = date.fromisoformat(from_day), date.fromisoformat(to_day)
    if end < start:
        raise ValueError('Ngày kết thúc trước ngày bắt đầu')
    if (end - start).days > 366:
        raise ValueError('Khoảng thời gian tối đa 1 năm')
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def today():
    return local_date(utc_now())


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lower, upper = int(k), min(int(k) + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (k - lower)


def _seconds(a, b):
    return (parse_iso(b) - parse_iso(a)).total_seconds()


def _summary(values):
    return {'n': len(values),
            'median_s': statistics.median(values) if values else None,
            'p90_s': percentile(values, 0.9),
            'mean_s': statistics.fmean(values) if values else None}


class MetricsService:
    def __init__(self, storage):
        self.storage = storage

    # ---------- nạp dữ liệu theo khoảng ngày ----------

    def _load(self, days):
        events, messages, suggestions, checks, presence = [], [], [], [], []
        for day in days:
            events += self.storage.events.by_day(day)
            messages += self.storage.messages.by_day(day)
            suggestions += self.storage.suggestions.by_day(day)
            checks += self.storage.guard_checks.by_day(day)
            presence += self.storage.presence.by_day(day)
        by_conv = defaultdict(list)
        for message in sorted(messages, key=lambda m: m.id):
            by_conv[message.conversation_id].append(message)
        return {'events': sorted(events, key=lambda e: e.id), 'messages': by_conv,
                'suggestions': suggestions, 'checks': checks,
                'presence': sorted(presence, key=lambda p: p.id)}

    # ---------- người trực ----------

    @staticmethod
    def _assignments(events, staff_id):
        """Các lần nhân sự được giao cuộc chat: (event, cách nhận)."""
        found = []
        for e in events:
            if e.type == 'claimed' and e.actor_id == staff_id:
                found.append((e, 'self'))
            elif e.type == 'assigned' and e.data.get('to') == staff_id:
                found.append((e, 'assigned'))
            elif e.type == 'transferred' and e.actor_id == staff_id:
                found.append((e, 'transfer'))
            elif e.type == 'reopened' and e.data.get('assignee') == staff_id:
                found.append((e, 'reopened'))
        return found

    def operator(self, staff_id, from_day, to_day, data=None):
        data = data or self._load(days_between(from_day, to_day))
        events, by_conv = data['events'], data['messages']
        assignments = self._assignments(events, staff_id)
        kinds = Counter(kind for _, kind in assignments)

        # Thời gian phản hồi đầu tiên: từ lúc được giao tới tin đầu tiên người đó gửi
        frt = []
        for event, _ in assignments:
            first = next((m for m in by_conv.get(event.conversation_id, [])
                          if m.sender_type == 'staff' and m.sender_id == staff_id
                          and m.created_at > event.created_at), None)
            if first:
                frt.append(_seconds(event.created_at, first.created_at))

        # Phản hồi trung bình: tin khách -> tin kế tiếp của người trực này. Chỉ tính tin
        # khách gửi SAU khi người trực đã được giao (thời gian chờ trước đó thuộc FRT/hàng chờ).
        assigned_at = defaultdict(list)
        for event, _ in assignments:
            assigned_at[event.conversation_id].append(event.created_at)
        response = []
        staff_messages = []
        for conv_id, messages in by_conv.items():
            for i, message in enumerate(messages):
                if message.sender_type == 'staff' and message.sender_id == staff_id:
                    staff_messages.append(message)
                if message.sender_type != 'end_user':
                    continue
                if not any(t <= message.created_at for t in assigned_at.get(conv_id, [])):
                    continue
                reply = next((m for m in messages[i + 1:] if m.sender_type == 'staff'), None)
                if reply and reply.sender_id == staff_id:
                    response.append(_seconds(message.created_at, reply.created_at))

        # Thời gian xử lý: được giao -> đóng (bởi chính người đó)
        handle = []
        for event, _ in assignments:
            closed = next((e for e in events if e.conversation_id == event.conversation_id
                           and e.type == 'closed' and e.actor_id == staff_id
                           and e.created_at > event.created_at), None)
            if closed:
                handle.append(_seconds(event.created_at, closed.created_at))

        modes = Counter(m.send_mode or 'typed' for m in staff_messages)
        total_sent = sum(modes.values())
        mine = [s for s in data['suggestions'] if s.staff_id == staff_id]
        edit = [s.edit_ratio for s in mine if s.edit_ratio is not None]
        checks = [c for c in data['checks'] if c.staff_id == staff_id]
        closed_convs = {e.conversation_id: e.created_at for e in events
                        if e.type == 'closed' and e.actor_id == staff_id}
        reopened = {e.conversation_id for e in events if e.type == 'reopened'
                    and e.conversation_id in closed_convs
                    and e.created_at > closed_convs[e.conversation_id]}

        return {
            'staff_id': staff_id, 'from_day': from_day, 'to_day': to_day,
            'conversations': {'total': len(assignments), 'self_claimed': kinds['self'],
                              'assigned_by_manager': kinds['assigned'],
                              'transferred_in': kinds['transfer'], 'reopened': kinds['reopened']},
            'first_response': _summary(frt),
            'response': _summary(response),
            'handle': _summary(handle),
            'ai_usage': {'messages': total_sent,
                         'ai_unedited': modes['ai_unedited'], 'ai_edited': modes['ai_edited'],
                         'typed': modes['typed'],
                         'pct_unedited': (modes['ai_unedited'] / total_sent) if total_sent else None,
                         'pct_edited': (modes['ai_edited'] / total_sent) if total_sent else None,
                         'mean_edit_ratio': statistics.fmean(edit) if edit else None,
                         'suggestions': len(mine),
                         'suggestions_discarded': sum(1 for s in mine if s.outcome == 'discarded')},
            'compliance': {
                'blocked': sum(1 for c in checks if c.verdict == 'block'),
                'blocked_sent_after_confirm': sum(1 for c in checks if c.verdict == 'block'
                                                  and c.confirmed_reason),
                'hard_blocked': sum(1 for c in checks if c.hard_block),
                'missing_monitoring_advice': sum(1 for c in checks
                                                 if 'missing_monitoring_advice' in c.issues),
            },
            'coordination': {
                'transfers_requested': sum(1 for e in events if e.type == 'transfer_requested'
                                           and e.actor_id == staff_id),
                'escalations': sum(1 for e in events if e.type == 'escalated'
                                   and e.actor_id == staff_id),
                'closed': len(closed_convs),
                'reopen_rate': (len(reopened) / len(closed_convs)) if closed_convs else None,
            },
            'satisfaction': {'n': 0, 'mean': None},   # khảo sát cuối cuộc chat chưa làm (UI-1.8)
            'on_duty_s': self._on_duty(data['presence'], staff_id, to_day),
        }

    @staticmethod
    def _on_duty(presence, staff_id, to_day):
        records = [p for p in presence if p.staff_id == staff_id]
        end_of_period = parse_iso(f'{to_day}T23:59:59+07:00')
        now = utc_now()
        total = 0.0
        for record, following in zip(records, records[1:] + [None]):
            if record.status != 'online':
                continue
            start = parse_iso(record.created_at)
            stop = parse_iso(following.created_at) if following else min(now, end_of_period)
            total += max(0.0, (stop - start).total_seconds())
        return total

    def compare(self, staff_ids, from_day, to_day):
        data = self._load(days_between(from_day, to_day))
        return [self.operator(s, from_day, to_day, data) for s in staff_ids]

    # ---------- vận hành ----------

    def overview(self, from_day, to_day):
        data = self._load(days_between(from_day, to_day))
        events, by_conv = data['events'], data['messages']
        created = {e.conversation_id: e for e in events if e.type == 'created'}
        handoffs = {e.conversation_id for e in events if e.type == 'mode_changed'}
        queued = [e for e in events if e.type in ('queued', 'escalated', 'returned_to_queue')]
        waits = []
        for q in queued:
            taken = next((e for e in events if e.conversation_id == q.conversation_id
                          and e.type in ('claimed', 'assigned') and e.created_at > q.created_at), None)
            if taken:
                waits.append(_seconds(q.created_at, taken.created_at))

        frt = []
        for e in events:
            assignee = e.actor_id if e.type in ('claimed', 'transferred') else (
                e.data.get('to') if e.type == 'assigned' else None)
            if not assignee:
                continue
            first = next((m for m in by_conv.get(e.conversation_id, [])
                          if m.sender_type == 'staff' and m.sender_id == assignee
                          and m.created_at > e.created_at), None)
            if first:
                frt.append(_seconds(e.created_at, first.created_at))

        levels, urgencies = Counter(), Counter()
        for conv_id in created:
            try:
                conversation = self.storage.conversations.get(conv_id)
            except KeyError:
                continue
            levels[conversation.required_level.value] += 1
            urgencies[conversation.urgency.value] += 1

        all_messages = [m for messages in by_conv.values() for m in messages]
        topics = Counter()
        for message in all_messages:
            for source in message.sources:
                title = (source.get('title') or '').split(' › ')[0]
                if title:
                    topics[title] += 1
        for suggestion in data['suggestions']:
            for source in suggestion.sources:
                title = (source.get('title') or '').split(' › ')[0]
                if title:
                    topics[title] += 1
        outcomes = Counter(s.outcome or 'pending' for s in data['suggestions'])
        on_duty = {p.staff_id for p in data['presence'] if p.status == 'online'}

        return {
            'from_day': from_day, 'to_day': to_day,
            'conversations': {'total': len(created), 'to_human': len(handoffs & set(created)),
                              'ai_only': len(set(created) - handoffs),
                              'end_users': len({e.actor_id for e in created.values() if e.actor_id})},
            'staff_on_duty': len(on_duty),
            'first_response': _summary(frt),
            'queue': {**_summary(waits), 'sla_breaches': sum(1 for e in events if e.type == 'sla_breached'),
                      'abandoned': None},
            'by_level': dict(levels), 'by_urgency': dict(urgencies),
            'emergencies': sum(1 for m in all_messages if m.kind == 'emergency'),
            'ai': {'answers': sum(1 for m in all_messages if m.sender_type == 'ai'),
                   'handoff_suggestions': sum(1 for m in all_messages if m.kind == 'handoff_suggestion'),
                   'suggestions': len(data['suggestions']), 'suggestion_outcomes': dict(outcomes)},
            'compliance': {'blocked': sum(1 for c in data['checks'] if c.verdict == 'block'),
                           'blocked_sent_after_confirm': sum(1 for c in data['checks']
                                                             if c.verdict == 'block' and c.confirmed_reason),
                           'hard_blocked': sum(1 for c in data['checks'] if c.hard_block)},
            'satisfaction': {'n': 0, 'mean': None},
            'top_topics': topics.most_common(8),
        }

    def _assigned_item(self, conversation, now, permissions):
        try:
            staff = self.storage.staff.get(conversation.assignee_id)
            name = f'{staff.title} {staff.display_name}'.strip()
            level = permissions.effective(staff.id)['level']
        except (KeyError, TypeError):
            name, level = '?', 'none'
        return {'id': conversation.id, 'required_level': conversation.required_level.value,
                'urgency': conversation.urgency.value, 'assignee_id': conversation.assignee_id,
                'assignee_name': name, 'assignee_level': level,
                'since_s': (now - parse_iso(conversation.assigned_at or conversation.created_at)).total_seconds()}

    def board(self):
        """Bảng trạng thái khung 3 (UI-3.3)."""

        presence = self.storage.presence.current()
        on_duty = Counter()
        from backend.services.permissions import PermissionService
        permissions = PermissionService(self.storage)
        for staff_id, record in presence.items():
            if record.status == 'online':
                on_duty[permissions.effective(staff_id)['level']] += 1
        waiting = self.storage.conversations.find(status='waiting')
        assigned = self.storage.conversations.find(status='assigned')
        now = utc_now()
        overview = self.overview(today(), today())
        return {
            'on_duty': dict(on_duty), 'on_duty_total': sum(on_duty.values()),
            'waiting': len(waiting), 'assigned': len(assigned),
            'waiting_items': [{'id': c.id, 'required_level': c.required_level.value,
                               'urgency': c.urgency.value, 'sla_breached': bool(c.sla_breached_at),
                               'waited_s': (now - parse_iso(c.queued_at or c.created_at)).total_seconds()}
                              for c in waiting],
            'assigned_items': [self._assigned_item(c, now, permissions) for c in assigned],
            'today': {'conversations': overview['conversations']['total'],
                      'first_response_median_s': overview['first_response']['median_s'],
                      'queue_median_s': overview['queue']['median_s'],
                      'blocked_sent_after_confirm': overview['compliance']['blocked_sent_after_confirm'],
                      'hard_blocked': overview['compliance']['hard_blocked']},
        }
