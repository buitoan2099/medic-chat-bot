"""
Backend FastAPI (technical plan mục 2). Chạy:

    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

BẮT BUỘC 1 worker và không --reload ở vận hành: backend là tiến trình duy nhất mở
Qdrant embedded (R1/R2). Không có Ollama vẫn chạy được: tìm tài liệu bằng BM25,
AI trả lời chuyển sang thông báo mời người trực.
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.llm.gateway import FakeAdapter, LLMGateway, OllamaAdapter, OpenAICompatibleAdapter
from backend.services.chat_service import ChatError, ChatService
from backend.services.config_service import ConfigError, ConfigService
from backend.services.index_manager import IndexManager, open_qdrant
from backend.services.triage import TriageService
from backend.storage.base import ConflictError, NotFoundError
from backend.storage.local import LocalStorage
from config import OPENAI_API_KEY, OPENAI_BASE_URL, STORAGE_DIR, sidecar_paths

log = logging.getLogger('backend')


@dataclass
class AppState:
    storage: object
    config: ConfigService
    gateway: LLMGateway
    index: IndexManager
    triage: TriageService
    chat: ChatService


def build_state(storage_dir=STORAGE_DIR, adapters=None, qdrant=True):
    storage = LocalStorage(storage_dir)
    config = ConfigService(storage)
    config.ensure_seeded()

    if adapters is None:
        adapters = {'ollama': OllamaAdapter(), 'fake': FakeAdapter()}
        # Provider ngoài chỉ được đăng ký khi có khoá; agent vẫn mặc định dùng Ollama (Q-5)
        if OPENAI_API_KEY:
            adapters['openai'] = OpenAICompatibleAdapter(OPENAI_API_KEY, OPENAI_BASE_URL)
    gateway = LLMGateway(adapters, max_parallel=config.settings()['llm_max_parallel'])

    client = None
    if qdrant:
        client = open_qdrant()          # lỗi rõ ràng nếu tiến trình khác giữ Qdrant (R2)
    index = IndexManager(client, config)
    triage = TriageService(gateway, config, storage)
    chat = ChatService(storage, config, gateway, triage, index)
    return AppState(storage, config, gateway, index, triage, chat)


def create_app(state_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.core = (state_factory or build_state)()
        from rag.lexical import get_index
        get_index(sidecar_paths(app.state.core.config.settings()['active_collection'])[1])
        yield
        client = app.state.core.index.client
        if client is not None:
            client.close()

    app = FastAPI(title='Medic Chat Bot – backend', version='0.1.0', lifespan=lifespan)
    from backend.api import admin, chat
    app.include_router(chat.router)
    app.include_router(admin.router)

    @app.get('/api/health')
    def health():
        core = app.state.core
        return {'status': 'ok', 'qdrant_open': core.index.client is not None,
                'active_collection': core.config.settings()['active_collection'],
                'llm_queue': core.gateway.limiter.queue_length}

    @app.exception_handler(NotFoundError)
    async def not_found(_, exc):
        return JSONResponse({'detail': f'Không tìm thấy: {exc}'}, status_code=404)

    @app.exception_handler(ConflictError)
    async def conflict(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ChatError)
    @app.exception_handler(ConfigError)
    async def bad_request(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    return app


app = create_app()
