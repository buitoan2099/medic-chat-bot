"""
Form trả lời chuẩn của quản lý (đặc tả 03 mục 7.3), dựng bằng CODE từ số liệu (BR-11).
Phần nhận định do AG-7 viết (nếu có) được gắn vào cuối form, ghi rõ là của AI.
"""

NO_DATA = 'Không có dữ liệu'


def dur(seconds):
    if seconds is None:
        return '—'
    seconds = int(round(seconds))
    if seconds < 3600:
        return f'{seconds // 60}′{seconds % 60:02d}″'
    return f'{seconds // 3600} giờ {seconds % 3600 // 60:02d}′'


def pct(value):
    return '—' if value is None else f'{value * 100:.0f}%'


def num(value, digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def _narrative(text):
    return f'\n\n**Nhận định (AI – cần quản lý thẩm định):**\n\n{text.strip()}' if text and text.strip() else ''


def conversation_summary(facts, narrative=None):
    """F-1."""
    lines = [f'### TÓM TẮT CUỘC TRÒ CHUYỆN #{facts["code"]}',
             f'- **Người dùng:** {facts["user"]} · **Người trực:** {facts["staff"] or "chưa có"} · '
             f'**Thời gian:** {facts["start"]} – {facts["end"] or "đang mở"}',
             f'- **Kênh:** {facts["channel"]}',
             f'- **Cấp cần thiết:** {facts["required_level"]} · **Mức khẩn:** {facts["urgency"]}',
             f'- **Hồ sơ ca chính:** {facts["profile"] or NO_DATA}',
             f'- **Tóm tắt (AG-5):** {facts["summary"] or NO_DATA}',
             f'- **Số tin:** khách {facts["counts"]["end_user"]} · AI {facts["counts"]["ai"]} · '
             f'người trực {facts["counts"]["staff"]}',
             f'- **Chuyển/đẩy cấp:** {facts["moves"] or "không"}',
             f'- **Kết quả:** {facts["status"]}',
             f'- **Điểm cần lưu ý:** {facts["alerts"] or "không"}']
    return '\n'.join(lines) + _narrative(narrative)


def operator_performance(name, level, m, group=None, narrative=None):
    """F-2. group: chỉ số trung bình nhóm để so sánh (tuỳ chọn)."""
    c, a, comp, co = m['conversations'], m['ai_usage'], m['compliance'], m['coordination']
    vs = lambda key: f' (nhóm: {dur(group[key])})' if group and group.get(key) is not None else ''  # noqa: E731
    lines = [f'### ĐÁNH GIÁ HIỆU SUẤT – {name} ({level}) · Kỳ: {m["from_day"]} – {m["to_day"]}',
             f'1. **Khối lượng:** {c["total"]} cuộc (tự nhận {c["self_claimed"]}, được chỉ định '
             f'{c["assigned_by_manager"]}, nhận chuyển {c["transferred_in"]}, mở lại {c["reopened"]}); '
             f'thời gian trực {dur(m["on_duty_s"])}',
             f'2. **Tốc độ:** phản hồi đầu tiên trung vị {dur(m["first_response"]["median_s"])}'
             f'{vs("frt_median")} / p90 {dur(m["first_response"]["p90_s"])}; phản hồi TB '
             f'{dur(m["response"]["mean_s"])}; xử lý TB {dur(m["handle"]["mean_s"])}',
             f'3. **Sử dụng AI:** {a["messages"]} tin – gửi nguyên {pct(a["pct_unedited"])}, sửa '
             f'{pct(a["pct_edited"])}, tự viết {a["typed"]}; mức sửa TB {pct(a["mean_edit_ratio"])}; '
             f'bỏ {a["suggestions_discarded"]}/{a["suggestions"]} gợi ý',
             f'4. **Tuân thủ:** {comp["blocked"]} cảnh báo vượt quyền (gửi sau xác nhận: '
             f'{comp["blocked_sent_after_confirm"]}, bị chặn cứng: {comp["hard_blocked"]}); thiếu '
             f'hướng dẫn theo dõi: {comp["missing_monitoring_advice"]}',
             f'5. **Phối hợp:** {co["transfers_requested"]} lần chuyển, {co["escalations"]} lần đẩy cấp, '
             f'đóng {co["closed"]} cuộc, tỉ lệ mở lại {pct(co["reopen_rate"])}',
             f'6. **Hài lòng của khách:** {NO_DATA} (khảo sát chưa triển khai)']
    return '\n'.join(lines) + _narrative(narrative)


def quality(facts, narrative=None):
    """F-3: thông tin nền; điểm rubric do AG-7 chấm nằm ở phần nhận định."""
    lines = [f'### ĐÁNH GIÁ CHẤT LƯỢNG – Cuộc chat #{facts["code"]}',
             f'- Người trực: {facts["staff"] or "chưa có"} · cấp cần thiết {facts["required_level"]} · '
             f'mức khẩn {facts["urgency"]}',
             f'- Cảnh báo kiểm tra trước khi gửi: {facts["alerts"] or "không"}',
             f'- Phản hồi đầu tiên: {facts.get("frt") or "—"}',
             '',
             '| Tiêu chí | Điểm (1–5) | Bằng chứng |', '|---|---|---|']
    for criterion in ('Đúng phạm vi cấp quyền', 'Chính xác so với tài liệu',
                      'Khai thác đủ thông tin (tuổi, dị ứng, thai...)',
                      'Có hướng dẫn theo dõi / khi nào đi khám', 'Xử lý dấu hiệu nặng/cấp cứu',
                      'Rõ ràng, dễ hiểu, thái độ', 'Thời gian phản hồi'):
        lines.append(f'| {criterion} | xem nhận định | |')
    body = '\n'.join(lines)
    if not narrative:
        body += '\n\n_Chưa chấm điểm: AG-7 không khả dụng. Quản lý/hội đồng chuyên môn đánh giá trực tiếp._'
    return body + _narrative(narrative)


def operations(o, narrative=None):
    """F-4."""
    q, ai, comp = o['queue'], o['ai'], o['compliance']
    topics = ', '.join(f'{t} ({n})' for t, n in o['top_topics']) or NO_DATA
    levels = ', '.join(f'{k}: {v}' for k, v in sorted(o['by_level'].items())) or NO_DATA
    urg = ', '.join(f'{k}: {v}' for k, v in sorted(o['by_urgency'].items())) or NO_DATA
    lines = [f'### BÁO CÁO VẬN HÀNH – {o["from_day"]}' + (f' → {o["to_day"]}' if o['to_day'] != o['from_day'] else ''),
             f'1. **Tổng quan:** {o["conversations"]["total"]} cuộc chat (chỉ AI {o["conversations"]["ai_only"]}, '
             f'chuyển người trực {o["conversations"]["to_human"]}), {o["conversations"]["end_users"]} người dùng, '
             f'{o["staff_on_duty"]} người trực đã trực',
             f'2. **Hàng chờ:** chờ trung vị {dur(q["median_s"])} / p90 {dur(q["p90_s"])}; quá SLA {q["sla_breaches"]}; '
             f'phản hồi đầu tiên trung vị {dur(o["first_response"]["median_s"])}; bỏ dở: {NO_DATA}',
             f'3. **Phân bố:** theo cấp – {levels}; theo mức khẩn – {urg}; thẻ cấp cứu đã hiện: {o["emergencies"]}',
             f'4. **AI:** {ai["answers"]} câu AI trả lời, {ai["handoff_suggestions"]} lần mời chuyển người trực, '
             f'{ai["suggestions"]} gợi ý copilot ({", ".join(f"{k}: {v}" for k, v in ai["suggestion_outcomes"].items()) or "—"})',
             f'5. **Tuân thủ:** {comp["blocked"]} cảnh báo vượt quyền (gửi sau xác nhận {comp["blocked_sent_after_confirm"]}), '
             f'{comp["hard_blocked"]} tin bị chặn cứng',
             f'6. **Hài lòng:** {NO_DATA}',
             f'7. **Chủ đề / thuốc được tra nhiều:** {topics}']
    return '\n'.join(lines) + _narrative(narrative)


def compare(rows, from_day, to_day, narrative=None):
    """F-5: bảng so sánh, có hàng trung bình nhóm; không xếp hạng năng lực chuyên môn."""
    lines = [f'### SO SÁNH NGƯỜI TRỰC · Kỳ: {from_day} – {to_day}', '',
             '| Người trực | Cấp | Số cuộc | FRT trung vị | Phản hồi TB | Xử lý TB | Gửi nguyên AI | Cảnh báo (gửi sau xác nhận) | Mở lại |',
             '|---|---|---|---|---|---|---|---|---|']
    for name, level, m in rows:
        lines.append(f'| {name} | {level} | {m["conversations"]["total"]} | {dur(m["first_response"]["median_s"])} | '
                     f'{dur(m["response"]["mean_s"])} | {dur(m["handle"]["mean_s"])} | '
                     f'{pct(m["ai_usage"]["pct_unedited"])} | {m["compliance"]["blocked"]} '
                     f'({m["compliance"]["blocked_sent_after_confirm"]}) | {pct(m["coordination"]["reopen_rate"])} |')
    if rows:
        avg = lambda vals: sum(vals) / len(vals) if vals else None  # noqa: E731
        frt = [m['first_response']['median_s'] for _, _, m in rows if m['first_response']['median_s'] is not None]
        lines.append(f'| **Trung bình nhóm** | | {avg([m["conversations"]["total"] for _, _, m in rows]):.1f} | '
                     f'{dur(avg(frt))} | | | | | |')
    return '\n'.join(lines) + _narrative(narrative)


def operator_workday(name, level, from_day, to_day, rows, narrative=None):
    """F-6: nội dung người trực đã xử lý trong khoảng ngày (mỗi cuộc chat một mục)."""
    period = from_day if from_day == to_day else f'{from_day} → {to_day}'
    closed = sum(1 for r in rows if r['status'] == 'closed')
    moved = sum(1 for r in rows if r['moves'])
    sent = sum(r['staff_messages'] for r in rows)
    lines = [f'### NỘI DUNG ĐÃ XỬ LÝ – {name} ({level}) · {period}',
             f'**{len(rows)} cuộc chat** · đã đóng {closed} · đang xử lý {len(rows) - closed} · '
             f'chuyển/đẩy cấp {moved} · {sent} tin đã gửi khách']
    if not rows:
        lines.append(f'\n{NO_DATA} – người trực chưa xử lý cuộc chat nào trong khoảng này.')
    for i, r in enumerate(rows, 1):
        lines.append(f'\n**{i}. #{r["code"]}** · {r["time"]} · {r["user"]} · cần {r["required_level"]}'
                     + (' · 🚨 cấp cứu' if r['urgency'] == 'emergency' else '')
                     + f' · **{STATUS_TEXT.get(r["status"], r["status"])}**')
        lines.append(f'- **Khách hỏi:** {r["issue"] or NO_DATA}')
        if r['summary']:
            lines.append(f'- **Tóm tắt (AG-5):** {r["summary"]}')
        if r['replies']:
            lines.append(f'- **Đã trả lời ({r["staff_messages"]} tin):** '
                         + ' / '.join(f'“{x}”' for x in r['replies']))
        else:
            lines.append('- **Đã trả lời:** chưa gửi tin nào')
        if r['ai_usage']:
            lines.append(f'- **Dùng gợi ý AI:** {r["ai_usage"]}')
        if r['moves']:
            lines.append(f'- **Chuyển/đẩy cấp:** {r["moves"]}')
        if r['alerts']:
            lines.append(f'- **Lưu ý:** {r["alerts"]}')
    return '\n'.join(lines) + _narrative(narrative)


STATUS_TEXT = {'closed': 'đã đóng', 'assigned': 'đang xử lý', 'waiting': 'đang chờ',
               'ai_active': 'chế độ AI'}
