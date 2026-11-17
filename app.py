import json
import re
import subprocess
import sys
import time

import streamlit as st

from config import (
    APP_NOTICE,
    APP_SUBTITLE,
    APP_TITLE,
    BASE_DIR,
    COLLECTION_NAME,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GENERATION_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    PDF_GLOB,
    QDRANT_DIR,
    STATE_FILE,
)
from provider.llm import check_generation_connection
from rag.lexical import get_index
from rag.rag import (
    close_vector_store,
    get_vector_store,
    prepare_answer,
    resume_vector_store,
    stream_answer,
)


PROVIDER_LABELS = {
    "ollama": "Ollama (Mac mini)",
    "gemini": "Gemini (Google AI)",
    "openai": "OpenAI / tương thích OpenAI",
}

PROVIDER_DEFAULT_MODELS = {
    "ollama": GENERATION_MODEL,
    "gemini": GEMINI_MODEL,
    "openai": OPENAI_MODEL,
}


st.set_page_config(page_title=APP_TITLE, page_icon="📚", layout="centered")


def read_ingest_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _empty_status(message="Chưa có dữ liệu embedding"):
    return {"exists": False, "status": "not_found", "points": 0, "vector_size": None,
            "message": message}


@st.cache_data(ttl=60, show_spinner=False)
def get_index_status():
    """
    Trạng thái chỉ mục: chỉ đếm số điểm trong Qdrant (nhanh), các thống kê
    khác (số chuyên luận, trang...) lấy từ file trạng thái ingest.
    """
    if not QDRANT_DIR.exists():
        return _empty_status()
    try:
        client = get_vector_store(wait_seconds=5)
        if not client.collection_exists(COLLECTION_NAME):
            return _empty_status()
        collection = client.get_collection(COLLECTION_NAME)
        vectors = collection.config.params.vectors
        vector_size = getattr(vectors, "size", None)
        if vector_size is None and isinstance(vectors, dict):
            vector_size = next((item.get("size") for item in vectors.values()
                                if isinstance(item, dict) and item.get("size")), None)
        points = client.count(collection_name=COLLECTION_NAME, exact=True).count
        return {"exists": True, "status": str(collection.status), "points": points,
                "vector_size": vector_size, "message": "Sẵn sàng"}
    except Exception as error:
        busy = "tiến trình khác" in str(error) or "lập chỉ mục lại" in str(error)
        return {
            **_empty_status(
                "Qdrant đang được tiến trình khác sử dụng"
                if busy
                else "Không đọc được trạng thái chỉ mục"
            ),
            "error": str(error),
        }


@st.cache_resource(show_spinner=False)
def warm_up():
    """Nạp trước chỉ mục BM25 (~5 giây) để câu hỏi đầu không bị chậm."""
    get_index()
    return True


def run_ingest(reset=False):
    """Chạy ingest trong tiến trình con sau khi nhả Qdrant của tiến trình này."""
    ingest_file = BASE_DIR / "rag" / "ingest.py"
    if not ingest_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {ingest_file}")
    # Chạy dạng module để import được config/rag từ thư mục gốc
    command = [sys.executable, "-u", "-m", "rag.ingest", "--reset" if reset else "--resume"]

    progress = st.progress(0, text="Đang khởi động embedding...")
    progress_status = st.empty()
    output_lines = []
    started = time.perf_counter()

    # Đóng client dùng chung và chặn mở lại cho tới khi ingest xong
    close_vector_store(pause=True)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            for line in process.stdout:
                line = line.rstrip()
                output_lines.append(line)

                progress_match = re.search(
                    r"(?:Đã lập chỉ mục\s+|Bỏ qua batch đã lập chỉ mục \()"
                    r"(\d+)/(\d+)(?: chunks|\))",
                    line,
                )
                if progress_match:
                    completed = int(progress_match.group(1))
                    total_chunks = int(progress_match.group(2))
                    percent = min(completed / total_chunks, 1.0) if total_chunks else 0
                    progress.progress(percent, text=f"Embedding: {completed:,}/{total_chunks:,} chunks")
                    progress_status.caption(
                        f"Đã xử lý {completed:,}/{total_chunks:,} chunks · "
                        f"Đã chạy {time.perf_counter() - started:.1f} giây"
                    )
                elif line:
                    progress_status.caption(line)

            return_code = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
    finally:
        resume_vector_store()
        get_index_status.clear()

    if return_code != 0:
        details = "\n".join(output_lines[-30:])
        raise RuntimeError(f"Ingest thất bại:\n{details}")

    progress.progress(1.0, text="Embedding hoàn tất")
    progress_status.caption(f"Hoàn tất sau {time.perf_counter() - started:.1f} giây")
    return "\n".join(output_lines)


def ensure_index():
    if read_ingest_state().get("status") == "in_progress":
        with st.spinner("Phát hiện embedding chưa hoàn tất. Đang tiếp tục..."):
            run_ingest(reset=False)
        return get_index_status()

    status = get_index_status()

    # Không được coi lỗi đọc chỉ mục (ví dụ Qdrant đang bị process khác giữ)
    # là "chưa có dữ liệu", nếu không sẽ kích hoạt rebuild toàn bộ ngoài ý muốn.
    if status.get("error"):
        raise RuntimeError(
            f"{status['message']}.\n{status['error']}\n"
            "Hãy tắt tiến trình đang dùng Qdrant rồi tải lại trang."
        )

    if status["exists"] and status["points"] > 0:
        return status
    with st.spinner("Chưa có chỉ mục. Đang tạo embedding lần đầu..."):
        run_ingest(reset=True)
    return get_index_status()


def display_index_status(status):
    state = read_ingest_state()
    st.sidebar.subheader("📊 Trạng thái dữ liệu")
    st.sidebar.caption(f"Collection: {COLLECTION_NAME}")
    st.sidebar.metric("Điểm / chunks", f"{status['points']:,}")
    st.sidebar.metric("Kích thước vector", status["vector_size"] or "—")
    st.sidebar.write(f"**Trạng thái:** {status['status']}")
    if state.get("pdf_files"):
        st.sidebar.write(f"**PDF:** {state['pdf_files']:,} file · {state.get('pdf_pages', 0):,} trang")
        st.sidebar.write(f"**Chủ đề (tiêu đề):** {state.get('topics', 0):,}")
        st.sidebar.write(f"**Loại mục lặp lại:** {state.get('section_types', 0):,}")
        st.sidebar.write(f"**Trang mục lục/chỉ mục (không embed):** {state.get('index_pages', 0):,}")
    if status.get("error"):
        st.sidebar.warning(status["error"])


def display_sources(sources):
    if not sources:
        return
    st.markdown("**📚 Tài liệu tham khảo**")
    for index, source in enumerate(sources, start=1):
        page, page_end = source.get("page", "—"), source.get("page_end")
        pages = f"trang {page}" if not page_end or page_end == page else f"trang {page}-{page_end}"
        title = source.get("title") or source.get("source_file", "")
        with st.expander(f"{index}. {title} — {pages}"):
            score = source.get("score")
            if score is not None:
                st.caption(f"Độ tương đồng vector: {score:.3f}")
            st.markdown(source.get("excerpt", ""))


def caption_for(metadata):
    parts = [f"🤖 {metadata.get('provider', '?')}:{metadata.get('model', '?')}",
             f"⏱️ {metadata.get('elapsed_seconds', 0):.2f} giây"]
    if metadata.get("carried"):
        parts.append("🔗 có dùng câu hỏi trước")
    parts.append(f"📚 {metadata.get('source_count', 0)} nguồn")
    return " · ".join(parts)


if "messages" not in st.session_state:
    st.session_state.messages = []

try:
    with st.spinner("Đang kiểm tra dữ liệu tài liệu..."):
        index_status = ensure_index()
        warm_up()
except Exception as error:
    st.error("Không thể khởi tạo dữ liệu tài liệu.")
    st.exception(error)
    st.stop()

display_index_status(index_status)

if get_index() is None:
    st.sidebar.warning("Chưa có chunks.jsonl cho collection này nên chưa bật tìm theo từ khoá. "
                       "Hãy rebuild chỉ mục.")

with st.sidebar.expander("🤖 Mô hình trả lời", expanded=True):
    provider_options = list(PROVIDER_LABELS)
    default_provider = LLM_PROVIDER if LLM_PROVIDER in provider_options else "ollama"

    provider = st.selectbox(
        "Provider",
        provider_options,
        index=provider_options.index(default_provider),
        format_func=lambda key: PROVIDER_LABELS[key],
        key="llm_provider",
    )

    model = st.text_input(
        "Model",
        value=PROVIDER_DEFAULT_MODELS[provider],
        key=f"llm_model_{provider}",
    ).strip()

    if provider == "ollama":
        st.caption("Không cần API key. Model chạy trên Mac mini.")
    elif provider == "gemini":
        st.caption(
            "🔑 Đã có GEMINI_API_KEY trong .env"
            if GEMINI_API_KEY
            else "⚠️ Thiếu GEMINI_API_KEY trong .env"
        )
    else:
        st.caption(f"🔗 {OPENAI_BASE_URL}")
        st.caption(
            "🔑 Đã có OPENAI_API_KEY trong .env"
            if OPENAI_API_KEY
            else "⚠️ Thiếu OPENAI_API_KEY trong .env"
        )

    st.caption("Embedding vẫn dùng Ollama (bge-m3) để khớp chỉ mục hiện có.")

    if st.button("🔌 Kiểm tra kết nối", use_container_width=True):
        ok, message = check_generation_connection(provider, model)
        if ok:
            st.success(message)
        else:
            st.error(message)

generation = {"provider": provider, "model": model}

with st.sidebar.expander("⚙️ Quản lý chỉ mục", expanded=False):
    st.caption(f"Nguồn: {PDF_GLOB}\n\nRebuild sẽ xóa collection hiện tại và tạo lại toàn bộ embedding.")
    confirm_rebuild = st.checkbox("Tôi xác nhận muốn xóa và tạo lại chỉ mục", key="confirm_rebuild")
    rebuild_clicked = st.button("🔄 Re-embed / rebuild chỉ mục", disabled=not confirm_rebuild,
                                use_container_width=True)

if st.sidebar.button("🧹 Xoá hội thoại", use_container_width=True):
    st.session_state.messages = []
    st.rerun()

if rebuild_clicked:
    try:
        with st.spinner("Đang đóng kết nối và tạo lại embedding..."):
            started = time.perf_counter()
            run_ingest(reset=True)
            elapsed = time.perf_counter() - started
        st.session_state.confirm_rebuild = False
        st.success(f"Đã rebuild chỉ mục trong {elapsed:.1f} giây.")
        st.rerun()
    except Exception as error:
        st.error("Không thể rebuild chỉ mục.")
        st.exception(error)


st.title(APP_TITLE)
st.caption(APP_SUBTITLE)
if APP_NOTICE:
    st.info(APP_NOTICE)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            metadata = message.get("metadata", {})
            if metadata:
                st.caption(caption_for(metadata))
            display_sources(message.get("sources", []))

question = st.chat_input("Nhập câu hỏi...")
if question:
    history = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        started = time.perf_counter()
        try:
            with st.spinner("Đang tra cứu tài liệu..."):
                prepared = prepare_answer(question, history=history)
            if prepared.get("warning"):
                st.warning(prepared["warning"])
            # Hiện chữ dần trong lúc mô hình sinh câu trả lời
            answer = st.write_stream(stream_answer(prepared, question, generation))
            if isinstance(answer, list):
                answer = "".join(str(part) for part in answer)
            elapsed = time.perf_counter() - started
            sources = prepared["sources"]
            metadata = {"elapsed_seconds": elapsed, "provider": provider, "model": model,
                        "carried": prepared["carried"],
                        "source_count": len({(s.get("source_file"), s.get("page")) for s in sources})}
            st.caption(caption_for(metadata))
            display_sources(sources)
            st.session_state.messages.append({"role": "assistant", "content": answer,
                                               "sources": sources, "metadata": metadata})
        except Exception as error:
            st.error("Đã xảy ra lỗi khi tra cứu tài liệu. Vui lòng thử lại sau.")
            st.exception(error)
