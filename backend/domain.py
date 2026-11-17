"""
Mô hình dữ liệu (đặc tả 04). Giai đoạn P1 gồm các thực thể cho khung 1 chế độ AI,
cấu hình agent và nhật ký. Thực thể của người trực / quản lý bổ sung ở P2–P3.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.core import iso, local_date, new_id, utc_now

SCHEMA_VERSION = 1


def _now():
    return iso(utc_now())


class Record(BaseModel):
    id: str = Field(default_factory=new_id)
    schema_version: int = SCHEMA_VERSION
    created_at: str = Field(default_factory=_now)


# ---------- người dùng & cuộc trò chuyện ----------

class EndUser(Record):
    display_name: Optional[str] = None
    consent_at: Optional[str] = None


class ConversationStatus(str, Enum):
    ai_active = 'ai_active'
    waiting = 'waiting'
    assigned = 'assigned'
    closed = 'closed'
    abandoned = 'abandoned'


class Level(str, Enum):
    none = 'none'
    C1 = 'C1'
    C2 = 'C2'
    C3 = 'C3'


LEVEL_ORDER = {Level.none: 0, Level.C1: 1, Level.C2: 2, Level.C3: 3}


class Urgency(str, Enum):
    normal = 'normal'
    soon = 'soon'
    emergency = 'emergency'


URGENCY_ORDER = {Urgency.normal: 0, Urgency.soon: 1, Urgency.emergency: 2}


class CaseProfile(BaseModel):
    """Hồ sơ ca (khai báo của khách; AG-5 bổ sung ở P2)."""

    age: Optional[str] = None
    sex: Optional[str] = None
    pregnant_or_breastfeeding: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    current_medications: Optional[str] = None


class Conversation(Record):
    end_user_id: str
    mode: str = 'ai'                      # ai | human
    status: ConversationStatus = ConversationStatus.ai_active
    required_level: Level = Level.none
    urgency: Urgency = Urgency.normal
    assignee_id: Optional[str] = None
    previous_conversation_id: Optional[str] = None
    profile: CaseProfile = Field(default_factory=CaseProfile)
    summary: str = ''
    summary_upto_message_id: Optional[str] = None
    days: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=_now)
    closed_at: Optional[str] = None
    version: int = 0                      # khoá lạc quan (BR-01)


class SenderType(str, Enum):
    end_user = 'end_user'
    ai = 'ai'
    staff = 'staff'
    system = 'system'


class Message(Record):
    conversation_id: str
    sender_type: SenderType
    sender_id: Optional[str] = None
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    kind: str = 'text'                    # text | emergency | handoff_suggestion | notice
    suggestion_id: Optional[str] = None
    send_mode: Optional[str] = None
    ai_run_id: Optional[str] = None
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


class ConversationEvent(Record):
    conversation_id: str
    type: str
    actor_type: str
    actor_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


# ---------- AI ----------

class AiRun(Record):
    agent_id: str
    prompt_version: Optional[int] = None
    provider: str
    model: str
    conversation_id: Optional[str] = None
    duration_s: Optional[float] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_prompt_tokens: Optional[int] = None
    status: str = 'ok'                    # ok | error | timeout | fallback
    error: Optional[str] = None
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


class AgentConfig(BaseModel):
    """Cấu hình vận hành của một agent (sửa được trên trang cấu hình model)."""

    agent_id: str
    title: str
    provider: str = 'ollama'              # ollama | gemini | openai | fake
    model: str = ''
    temperature: float = 0.1
    max_tokens: int = 1024
    num_ctx: int = 16384
    timeout_s: float = 120.0
    enabled: bool = True
    active_prompt_version: int = 1
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None


class PromptVersion(BaseModel):
    agent_id: str
    version: int
    note: str = ''
    created_by: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class AuditLog(Record):
    actor: str
    action: str
    target: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
