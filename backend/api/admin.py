"""API quản trị: cấu hình agent/model, prompt, cài đặt, chỉ mục, tìm kiếm tài liệu."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.common import get_core, require_admin
from backend.llm.gateway import PRIORITY_INTERACTIVE, LLMError
from rag import rag

router = APIRouter(prefix='/api/admin', tags=['quản trị'], dependencies=[Depends(require_admin)])


class AgentUpdate(BaseModel):
    changes: dict[str, Any]


class PromptCreate(BaseModel):
    text: str
    note: str = ''
    activate: bool = False


class SettingsUpdate(BaseModel):
    changes: dict[str, Any]


class TestRequest(BaseModel):
    sample: bool = False
    question: str = 'Xin chào, bạn là ai?'


# ---------- agent & model ----------

@router.get('/agents')
def agents(core=Depends(get_core)):
    return {agent_id: cfg.model_dump() for agent_id, cfg in core.config.agents().items()}


@router.put('/agents/{agent_id}')
def update_agent(agent_id: str, body: AgentUpdate, core=Depends(get_core),
                 actor=Depends(require_admin)):
    return core.config.update_agent(agent_id, body.changes, actor).model_dump()


@router.post('/agents/{agent_id}/test')
def test_agent(agent_id: str, body: TestRequest, core=Depends(get_core)):
    """Kiểm tra kết nối; sample=True gửi thêm một câu hỏi mẫu và đo thời gian."""

    cfg = core.config.agent(agent_id)
    ok, message = core.gateway.ping(cfg.provider, cfg.model)
    result = {'ok': ok, 'message': message}
    if ok and body.sample:
        prompt, _ = core.config.prompt(agent_id)
        try:
            response = core.gateway.chat(cfg, [{'role': 'system', 'content': prompt},
                                               {'role': 'user', 'content': body.question}],
                                         PRIORITY_INTERACTIVE)
            result['sample'] = {'text': response.text[:2000], 'duration_s': response.duration_s,
                                'model': response.model}
        except LLMError as error:
            result.update(ok=False, message=f'Chạy thử lỗi: {error}')
    return result


@router.get('/agents/{agent_id}/prompts')
def prompt_versions(agent_id: str, core=Depends(get_core)):
    active = core.config.agent(agent_id).active_prompt_version
    return {'active': active,
            'versions': [v.model_dump() for v in core.config.prompt_versions(agent_id)]}


@router.get('/agents/{agent_id}/prompts/{version}')
def prompt_text(agent_id: str, version: int, core=Depends(get_core)):
    return {'version': version, 'text': core.storage.config.get_prompt(agent_id, version)}


@router.post('/agents/{agent_id}/prompts')
def add_prompt(agent_id: str, body: PromptCreate, core=Depends(get_core),
               actor=Depends(require_admin)):
    return core.config.add_prompt_version(agent_id, body.text, body.note, actor,
                                          activate=body.activate).model_dump()


@router.post('/agents/{agent_id}/prompts/{version}/activate')
def activate_prompt(agent_id: str, version: int, core=Depends(get_core),
                    actor=Depends(require_admin)):
    return core.config.activate_prompt(agent_id, version, actor).model_dump()


# ---------- cài đặt ----------

@router.get('/settings')
def settings(core=Depends(get_core)):
    return core.config.settings()


@router.put('/settings')
def update_settings(body: SettingsUpdate, core=Depends(get_core), actor=Depends(require_admin)):
    updated = core.config.update_settings(body.changes, actor)
    if 'llm_max_parallel' in body.changes:
        core.gateway.limiter.set_max_parallel(updated['llm_max_parallel'])
    return updated


# ---------- chỉ mục ----------

@router.get('/index')
def index_status(core=Depends(get_core)):
    return core.index.status()


@router.post('/index/rebuild')
def rebuild(core=Depends(get_core), actor=Depends(require_admin)):
    try:
        return core.index.start_rebuild(actor)
    except RuntimeError as error:
        raise HTTPException(409, str(error))


@router.post('/index/cancel')
def cancel(core=Depends(get_core)):
    core.index.cancel()
    return core.index.status()


@router.post('/index/rollback')
def rollback(core=Depends(get_core), actor=Depends(require_admin)):
    try:
        return core.index.rollback(actor)
    except RuntimeError as error:
        raise HTTPException(409, str(error))


@router.get('/search')
def search(q: str, method: str = 'hybrid', k: int = 10, collection: Optional[str] = None,
           core=Depends(get_core)):
    """Tra tài liệu cho evaluation/quản trị: hybrid | bm25 | dense."""

    collection = collection or core.config.settings()['active_collection']
    client = core.index.client
    if method == 'dense':
        if not core.index.has_vectors(collection):
            raise HTTPException(409, f'Collection {collection} chưa có vector (chưa embed)')
        from rag.embeddings import embed_query
        try:
            vector = embed_query(q)
        except RuntimeError as error:
            raise HTTPException(503, str(error))
        points = client.query_points(collection_name=collection, query=vector, limit=k,
                                     with_payload=True).points
        results = [{'text': (p.payload or {}).get('page_content', ''),
                    'metadata': (p.payload or {}).get('metadata', {}), 'score': p.score}
                   for p in points]
        return {'results': results, 'warning': None}
    if method not in ('hybrid', 'bm25'):
        raise HTTPException(400, 'method phải là hybrid | bm25 | dense')
    result = rag.retrieve(q, k=k, client=client,
                          use_dense=(method == 'hybrid' and core.index.has_vectors(collection)),
                          collection=collection, min_score=None)
    return {'results': result['results'], 'warning': result.get('warning')}


# ---------- nhân sự & quyền (P2; trang phân quyền đầy đủ ở P3) ----------

class StaffCreate(BaseModel):
    username: str
    display_name: str
    password: str
    title: str = ''
    roles: list[str] = ['operator']


class CredentialUpdate(BaseModel):
    credential: dict
    verify: bool = False


class GrantRequest(BaseModel):
    key: str
    value: Any
    reason: str
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None


class PasswordUpdate(BaseModel):
    password: str


class ActiveUpdate(BaseModel):
    active: bool


def _staff_out(core, staff):
    return {**staff.model_dump(mode='json', exclude={'password_hash'}),
            'effective': core.permissions.effective(staff.id),
            'presence': core.permissions.presence(staff.id)}


@router.get('/staff')
def list_staff(core=Depends(get_core)):
    return [_staff_out(core, s) for s in core.storage.staff.all()]


@router.post('/staff')
def create_staff(body: StaffCreate, core=Depends(get_core), actor=Depends(require_admin)):
    staff = core.permissions.create_staff(body.username, body.display_name, body.password, actor,
                                          body.title, body.roles)
    return _staff_out(core, staff)


@router.put('/staff/{staff_id}/credential')
def set_credential(staff_id: str, body: CredentialUpdate, core=Depends(get_core),
                   actor=Depends(require_admin)):
    return _staff_out(core, core.permissions.set_credential(staff_id, body.credential, actor,
                                                            body.verify))


@router.post('/staff/{staff_id}/grants')
def grant(staff_id: str, body: GrantRequest, core=Depends(get_core), actor=Depends(require_admin)):
    core.permissions.grant(staff_id, body.key, body.value, actor, body.reason,
                           body.effective_from, body.effective_to)
    return _staff_out(core, core.storage.staff.get(staff_id))


@router.get('/staff/{staff_id}/grants')
def grants(staff_id: str, core=Depends(get_core)):
    return [g.model_dump(mode='json') for g in core.storage.permissions.for_staff(staff_id)]


@router.put('/staff/{staff_id}/password')
def password(staff_id: str, body: PasswordUpdate, core=Depends(get_core),
             actor=Depends(require_admin)):
    core.permissions.set_password(staff_id, body.password, actor)
    return {'ok': True}


@router.put('/staff/{staff_id}/active')
def active(staff_id: str, body: ActiveUpdate, core=Depends(get_core), actor=Depends(require_admin)):
    core.permissions.set_active(staff_id, body.active, actor)
    return _staff_out(core, core.storage.staff.get(staff_id))
