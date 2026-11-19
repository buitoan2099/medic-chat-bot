"""
Backend FastAPI (technical plan mục 2). Chạy:

    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

BẮT BUỘC 1 worker và không --reload ở vận hành: backend là tiến trình duy nhất mở
Qdrant embedded (R1/R2). Không có Ollama vẫn chạy được: tìm tài liệu bằng BM25,
AI trả lời chuyển sang thông báo mời người trực.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.llm.gateway import FakeAdapter, LLMGateway, OllamaAdapter, OpenAICompatibleAdapter
from backend.services.chat_service import ChatError, ChatService
from backend.services.config_service import ConfigError, ConfigService
from backend.services.auth import AuthError, TokenSigner
from backend.services.copilot import CaseMemoryService, CopilotService
from backend.services.guard import GuardService
from backend.services.index_manager import IndexManager, open_qdrant
from backend.services.manager_agent import ManagerAgentService, ManagerError
from backend.services.metrics import MetricsService
from backend.services.operator_service import OperatorError, OperatorService, SlaMonitor
from backend.services.permissions import PermissionError_, PermissionService
from backend.services.triage import TriageService
from backend.storage.base import ConflictError, NotFoundError
from backend.storage.local import LocalStorage
from config import AUTH_SECRET, DEMO_MODE, OPENAI_API_KEY, OPENAI_BASE_URL, STORAGE_DIR, sidecar_paths

log = logging.getLogger('backend')


class InlineExecutor:
    """Chạy ngay trong luồng gọi (dùng cho test để kết quả xác định)."""

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:   # giữ lỗi trong future như executor thật
            future.set_exception(error)
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        pass


class LoggingExecutor(ThreadPoolExecutor):
    """Executor nền ghi log lỗi của tác vụ (copilot, AG-5) thay vì nuốt im lặng."""

    def submit(self, fn, *args, **kwargs):
        future = super().submit(fn, *args, **kwargs)
        future.add_done_callback(lambda f: f.exception() and log.error(
            'Tác vụ nền %s lỗi: %r', getattr(fn, '__qualname__', fn), f.exception()))
        return future


@dataclass
class AppState:
    storage: object
    config: ConfigService
    gateway: LLMGateway
    index: IndexManager
    triage: TriageService
    chat: ChatService
    permissions: PermissionService
    signer: TokenSigner
    operator: OperatorService
    background: object
    manager: object = None
    metrics: object = None
    sla: object = None
    demo: bool = False


def build_state(storage_dir=STORAGE_DIR, adapters=None, qdrant=True, background='thread',
                auth_secret=None, demo=None):
    storage = LocalStorage(storage_dir)
    config = ConfigService(storage)
    config.ensure_seeded()

    if adapters is None:
        adapters = {'ollama': OllamaAdapter(), 'fake': FakeAdapter()}
        # Provider ngoài chỉ được đăng ký khi có khoá; agent vẫn mặc định dùng Ollama (Q-5)
        if OPENAI_API_KEY:
            adapters['openai'] = OpenAICompatibleAdapter(OPENAI_API_KEY, OPENAI_BASE_URL)
    gateway = LLMGateway(adapters, max_parallel=config.settings()['llm_max_parallel'])
    gateway.limiter.set_reserved(config.settings().get('llm_reserved_slots', 1))

    client = None
    if qdrant:
        client = open_qdrant()          # lỗi rõ ràng nếu tiến trình khác giữ Qdrant (R2)
    index = IndexManager(client, config)
    triage = TriageService(gateway, config, storage)
    executor = InlineExecutor() if background == 'inline' else LoggingExecutor(
        max_workers=4, thread_name_prefix='ai-bg')
    permissions = PermissionService(storage)
    if not (auth_secret or AUTH_SECRET):
        log.warning('Chưa đặt AUTH_SECRET: token đăng nhập sẽ mất hiệu lực khi khởi động lại')
    signer = TokenSigner(auth_secret or AUTH_SECRET or None)
    copilot = CopilotService(gateway, config, storage, index)
    case_memory = CaseMemoryService(gateway, config, storage)
    guard = GuardService(gateway, config, storage)
    operator = OperatorService(storage, permissions, config, copilot, case_memory, guard, executor)
    chat = ChatService(storage, config, gateway, triage, index, operator=operator,
                       case_memory=case_memory, background=executor)
    sla = SlaMonitor(operator) if background != 'inline' else None
    manager = ManagerAgentService(storage, gateway, config, permissions, operator, index)
    demo = DEMO_MODE if demo is None else demo
    if demo:
        from backend.services.demo import ensure_demo_accounts
        ensure_demo_accounts(storage, permissions)
        log.warning('DEMO_MODE đang bật: có tài khoản demo_* đăng nhập không cần mật khẩu')
    return AppState(storage, config, gateway, index, triage, chat, permissions, signer, operator,
                    executor, manager, MetricsService(storage), sla, demo)


def create_app(state_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.core = (state_factory or build_state)()
        from rag.lexical import get_index
        get_index(sidecar_paths(app.state.core.config.settings()['active_collection'])[1])
        if app.state.core.sla is not None:
            app.state.core.sla.start()
        yield
        if app.state.core.sla is not None:
            app.state.core.sla.stop()
        # Huỷ tác vụ AI nền chưa chạy để tắt nhanh (tác vụ đang gọi Ollama vẫn phải chờ hết)
        app.state.core.background.shutdown(wait=False, cancel_futures=True)
        client = app.state.core.index.client
        if client is not None:
            client.close()

    app = FastAPI(title='Medic Chat Bot – backend', version='0.1.0', lifespan=lifespan)
    from backend.api import admin, chat, manager, operator
    app.include_router(chat.router)
    app.include_router(manager.router)
    app.include_router(admin.router)
    app.include_router(operator.router)
    app.include_router(operator.manager_router)

    @app.get('/api/health')
    def health():
        core = app.state.core
        job = core.index.job
        return {'status': 'ok', 'qdrant_open': core.index.client is not None,
                'active_collection': core.config.settings()['active_collection'],
                # Home dùng để báo khách khi chỉ mục chưa sẵn sàng (tra cứu chỉ bằng từ khoá)
                'vectors_ready': core.index.has_vectors(),
                'index_job_running': bool(job and job.status == 'running'),
                'llm_queue': core.gateway.limiter.queue_length}

    @app.exception_handler(NotFoundError)
    async def not_found(_, exc):
        return JSONResponse({'detail': f'Không tìm thấy: {exc}'}, status_code=404)

    @app.exception_handler(ConflictError)
    async def conflict(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ChatError)
    @app.exception_handler(ConfigError)
    @app.exception_handler(OperatorError)
    @app.exception_handler(ManagerError)
    @app.exception_handler(ValueError)
    async def bad_request(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(PermissionError_)
    async def forbidden(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=403)

    @app.exception_handler(AuthError)
    async def unauthorized(_, exc):
        return JSONResponse({'detail': str(exc)}, status_code=401)

    return app


app = create_app()
