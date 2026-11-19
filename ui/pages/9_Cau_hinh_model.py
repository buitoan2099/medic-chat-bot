"""Trang cấu hình model (đặc tả 02 mục 4) – bản P1: agent, prompt, cài đặt, chỉ mục."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ui import api_client as api  # noqa: E402

st.set_page_config(page_title='Cấu hình model', page_icon='⚙️', layout='wide')
st.title('⚙️ Cấu hình model')

state = st.session_state
token = st.sidebar.text_input('Khoá quản trị (ADMIN_TOKEN)', type='password',
                              value=state.get('admin_token', ''))
if not token:
    st.info('Nhập khoá quản trị ở thanh bên để tiếp tục.')
    st.stop()
state.admin_token = token
admin = api.Admin(token)

try:
    agents = admin.agents()
except api.BackendError as error:
    st.error(f'Không truy cập được: {error}')
    st.stop()

PROVIDERS = ['ollama', 'fake', 'gemini', 'openai']
st.caption('Provider bên ngoài (gemini/openai) **mặc định không dùng**: dữ liệu chat không được '
           'gửi ra ngoài khi chưa được duyệt (Q-5). `fake` chỉ để chạy thử.')

tab_agents, tab_prompts, tab_settings, tab_index = st.tabs(
    ['Agent & model', 'Prompt', 'Cài đặt', 'Chỉ mục tài liệu'])

# ---------- agent & model ----------

with tab_agents:
    for agent_id, cfg in agents.items():
        with st.expander(f'{cfg["title"]} (`{agent_id}`)', expanded=True):
            with st.form(f'agent-{agent_id}'):
                c1, c2, c3 = st.columns(3)
                provider = c1.selectbox('Provider', PROVIDERS, index=PROVIDERS.index(cfg['provider'])
                                        if cfg['provider'] in PROVIDERS else 0)
                model = c2.text_input('Model', cfg['model'])
                enabled = c3.checkbox('Bật', cfg['enabled'])
                c4, c5, c6, c7 = st.columns(4)
                temperature = c4.number_input('Nhiệt độ', 0.0, 2.0, float(cfg['temperature']), 0.05)
                max_tokens = c5.number_input('Token tối đa', 16, 8192, int(cfg['max_tokens']), 64)
                num_ctx = c6.number_input('num_ctx', 2048, 65536, int(cfg['num_ctx']), 1024)
                timeout_s = c7.number_input('Timeout (s)', 1.0, 900.0, float(cfg['timeout_s']), 5.0)
                c8, c9 = st.columns(2)
                fb_provider = c8.selectbox('Provider dự phòng', [''] + PROVIDERS,
                                           index=([''] + PROVIDERS).index(cfg.get('fallback_provider') or ''))
                fb_model = c9.text_input('Model dự phòng', cfg.get('fallback_model') or '')
                if st.form_submit_button('Lưu', type='primary'):
                    try:
                        admin.update_agent(agent_id, {
                            'provider': provider, 'model': model.strip(), 'enabled': enabled,
                            'temperature': temperature, 'max_tokens': int(max_tokens),
                            'num_ctx': int(num_ctx), 'timeout_s': timeout_s,
                            'fallback_provider': fb_provider or None,
                            'fallback_model': fb_model.strip() or None})
                        st.success('Đã lưu. Áp dụng từ tin nhắn tiếp theo.')
                    except api.BackendError as error:
                        st.error(str(error))
            b1, b2 = st.columns(2)
            if b1.button('🔌 Kiểm tra kết nối', key=f'ping-{agent_id}'):
                result = admin.test_agent(agent_id)
                (st.success if result['ok'] else st.error)(result['message'])
            if b2.button('▶️ Chạy thử câu mẫu', key=f'sample-{agent_id}'):
                with st.spinner('Đang chạy thử...'):
                    result = admin.test_agent(agent_id, sample=True)
                if result.get('sample'):
                    st.success(f'{result["sample"]["model"]} · {result["sample"]["duration_s"]:.1f}s')
                    st.markdown(result['sample']['text'])
                else:
                    st.error(result['message'])

# ---------- prompt ----------

with tab_prompts:
    agent_id = st.selectbox('Agent', list(agents), format_func=lambda a: agents[a]['title'])
    info = admin.prompts(agent_id)
    st.write(f'Phiên bản đang dùng: **v{info["active"]}**')
    rows = [{'Phiên bản': v['version'], 'Ghi chú': v['note'], 'Người tạo': v.get('created_by'),
             'Thời điểm (UTC)': v['created_at']} for v in info['versions']]
    st.dataframe(rows, hide_index=True, width='stretch')
    version = st.selectbox('Xem phiên bản', [v['version'] for v in info['versions']],
                           index=len(info['versions']) - 1)
    text = admin.prompt_text(agent_id, version)
    st.text_area('Nội dung', text, height=300, disabled=True, key=f'view-{agent_id}-{version}')
    if version != info['active'] and st.button(f'Dùng phiên bản v{version}'):
        admin.activate_prompt(agent_id, version)
        st.rerun()

    st.divider()
    st.subheader('Tạo phiên bản mới')
    st.warning('Đổi prompt ảnh hưởng trực tiếp tới câu trả lời. Nên chạy bộ câu hỏi kiểm thử trước khi dùng.')
    with st.form(f'new-prompt-{agent_id}'):
        new_text = st.text_area('Prompt', text, height=300)
        note = st.text_input('Ghi chú thay đổi (bắt buộc)')
        activate = st.checkbox('Dùng ngay sau khi tạo')
        if st.form_submit_button('Tạo phiên bản'):
            if not note.strip():
                st.error('Cần ghi chú thay đổi.')
            else:
                try:
                    created = admin.add_prompt(agent_id, new_text, note.strip(), activate)
                    st.success(f'Đã tạo v{created["version"]}')
                except api.BackendError as error:
                    st.error(str(error))

# ---------- cài đặt ----------

with tab_settings:
    settings = admin.settings()
    with st.form('settings'):
        parallel = st.number_input('Số yêu cầu LLM song song (khớp OLLAMA_NUM_PARALLEL)', 1, 16,
                                   int(settings['llm_max_parallel']))
        top_k = st.number_input('Số đoạn tài liệu đưa vào ngữ cảnh (TOP_K)', 1, 20, int(settings['top_k']))
        min_score = st.number_input('Ngưỡng cosine tối thiểu (chế độ AI)', 0.0, 1.0,
                                    float(settings['min_score']), 0.01)
        st.caption(f'Bộ quy tắc phân tầng (phan-tang.md): '
                   f'{"BẬT" if settings["tiering_rules_enabled"] else "TẮT – chờ Hội đồng duyệt"}')
        if st.form_submit_button('Lưu', type='primary'):
            admin.update_settings({'llm_max_parallel': int(parallel), 'top_k': int(top_k),
                                   'min_score': float(min_score)})
            st.success('Đã lưu.')

# ---------- chỉ mục ----------

with tab_index:
    status = admin.index()
    c1, c2, c3 = st.columns(3)
    c1.metric('Collection đang dùng', status['active_collection'])
    c2.metric('Điểm trong Qdrant', status['points'] if status['points'] is not None else 'chưa có')
    c3.metric('Chunk (BM25)', status['chunks'])
    if status['points'] is None:
        st.warning('Collection đang dùng chưa có vector (chưa embed). Tìm kiếm chạy bằng BM25.')
    st.caption(f'Collection trước (để quay lại): {status.get("previous_collection") or "—"}')

    job = status.get('job')
    if job:
        st.write(f'**Lập chỉ mục gần nhất:** {job["collection"]} · {job["status"]}'
                 + (f' · lỗi: {job["error"]}' if job.get('error') else ''))
        if job.get('total'):
            st.progress(min(job['done'] / job['total'], 1.0))
        if job.get('progress_text'):
            st.caption(job['progress_text'])
        st.code('\n'.join(job['log_tail']) or '(chưa có log)', language=None)

    for item in status.get('resumable', []):
        where = 'collection đang dùng' if item['is_active'] else 'lần dựng lại bị ngắt'
        st.warning(f'Lập chỉ mục dở dang ({where}) `{item["collection"]}`: '
                   f'{item["completed_chunks"]:,}/{item["total_chunks"] or 0:,} chunk.')
        if st.button(f'▶️ Tiếp tục {item["collection"]}', key=f'resume-{item["collection"]}'):
            try:
                admin.resume_index(item['collection'])
                st.success('Đã tiếp tục. Bấm "Làm mới" để xem tiến độ.')
            except api.BackendError as error:
                st.error(str(error))

    b1, b2, b3, b4 = st.columns(4)
    b1.button('🔄 Làm mới')
    confirm = st.checkbox('Tôi hiểu: dựng chỉ mục mới song song (cần Ollama), xong mới chuyển sang')
    if b2.button('Dựng lại chỉ mục', disabled=not confirm):
        try:
            admin.rebuild()
            st.success('Đã bắt đầu. Bấm "Làm mới" để xem tiến độ.')
        except api.BackendError as error:
            st.error(str(error))
    if job and job['status'] == 'running' and b3.button('Huỷ'):
        admin.cancel_rebuild()
    if status.get('previous_collection') and b4.button('↩️ Quay lại collection trước'):
        try:
            admin.rollback()
            st.rerun()
        except api.BackendError as error:
            st.error(str(error))
