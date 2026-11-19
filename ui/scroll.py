"""Cuộn trang xuống tin nhắn mới nhất (Streamlit không tự cuộn sau khi chạy lại trang)."""

import streamlit as st

_SCRIPT = """
<script>
setTimeout(() => {
  const targets = [
    document.querySelector('[data-testid="stMain"]'),
    document.querySelector('[data-testid="stAppScrollToBottomContainer"]'),
    document.querySelector('section.main'),
    document.scrollingElement,
  ];
  for (const el of targets) {
    if (el && el.scrollHeight > el.clientHeight) el.scrollTo({top: el.scrollHeight, behavior: 'smooth'});
  }
}, 150);
</script>
<span data-mark="%s"></span>
"""


def scroll_to_bottom(key, count):
    """Cuộn xuống cuối khi số tin nhắn `count` thay đổi (không cuộn khi chỉ làm mới định kỳ,
    để người dùng còn kéo lên đọc tin cũ)."""

    state_key = f'_scrolled_{key}'
    if st.session_state.get(state_key) == count:
        return
    st.session_state[state_key] = count
    st.html(_SCRIPT % f'{key}-{count}', unsafe_allow_javascript=True)


def waiting_indicator(label, since_iso, key):
    """Dòng chờ có vòng xoay + đồng hồ đếm từ `since_iso`, chạy bằng JS (nhảy đều từng giây)."""
    from html import escape
    st.html(f"""
<div style="display:flex;align-items:center;gap:.6rem;opacity:.85;padding:.4rem 0">
  <div class="wait-dot"></div>
  <span>{escape(label)}… <b id="wait-{key}"></b></span>
</div>
<style>.wait-dot{{width:.8rem;height:.8rem;border-radius:50%;border:2px solid currentColor;
border-top-color:transparent;animation:wait-spin .8s linear infinite;flex:none}}
@keyframes wait-spin{{to{{transform:rotate(360deg)}}}}</style>
<script>
(() => {{
  const start = Date.parse({since_iso!r});
  const fmt = s => s < 60 ? s + 's' : Math.floor(s / 60) + ' phút ' + String(s % 60).padStart(2, '0') + 's';
  const tick = () => {{
    const el = document.getElementById('wait-{key}');
    if (!el) {{ clearInterval(timer); return; }}
    el.textContent = fmt(Math.max(0, Math.floor((Date.now() - start) / 1000)));
  }};
  const timer = setInterval(tick, 1000);
  tick();
}})();
</script>""", unsafe_allow_javascript=True)
