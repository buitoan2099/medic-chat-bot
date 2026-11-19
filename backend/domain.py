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
    chief_complaint: Optional[str] = None      # triệu chứng chính
    onset: Optional[str] = None                # thời gian khởi phát
    severity: Optional[str] = None             # mức độ
    needs_confirmation: list[str] = Field(default_factory=list)   # thông tin mâu thuẫn


class Conversation(Record):
    end_user_id: str
    mode: str = 'ai'                      # ai | human
    status: ConversationStatus = ConversationStatus.ai_active
    required_level: Level = Level.none
    urgency: Urgency = Urgency.normal
    assignee_id: Optional[str] = None
    previous_conversation_id: Optional[str] = None
    profile: CaseProfile = Field(default_factory=CaseProfile)
    # Nguồn của từng trường hồ sơ ca: user | ai | staff (bản người trực sửa luôn ưu tiên)
    profile_sources: dict[str, str] = Field(default_factory=dict)
    summary: str = ''
    summary_upto_message_id: Optional[str] = None
    days: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=_now)
    closed_at: Optional[str] = None
    queued_at: Optional[str] = None       # lúc vào hàng chờ (tính SLA)
    assigned_at: Optional[str] = None
    sla_breached_at: Optional[str] = None
    # Đề nghị chuyển đang chờ người nhận chấp nhận (BR-04)
    pending_transfer: Optional[dict[str, Any]] = None
    case_memory_upto: Optional[str] = None   # AG-5 đã xử lý tới tin nào
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
    sender_name: Optional[str] = None     # tên + chức danh người trực hiển thị cho khách (UI-1.6)
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
    queue_wait_s: Optional[float] = None     # thời gian xếp hàng chờ LLM (trước khi chạy)
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


# ---------- nhân sự & quyền (P2) ----------

class Credential(BaseModel):
    """Chứng chỉ chuyên môn (đặc tả 02 mục 5). C2/C3 cần chứng chỉ đã xác minh, còn hạn."""

    kind: str                              # vd: bac_si | duoc_si | y_si | dieu_duong
    number: str = ''
    issued_by: str = ''
    expires_at: Optional[str] = None       # 'YYYY-MM-DD' hoặc None (không thời hạn)
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None


class Staff(Record):
    username: str
    display_name: str
    title: str = ''                        # chức danh hiển thị cho khách (UI-1.6)
    roles: list[str] = Field(default_factory=lambda: ['operator'])   # operator | manager | admin
    password_hash: str = ''
    active: bool = True
    credential: Optional[Credential] = None
    updated_at: str = Field(default_factory=_now)


class PermissionGrant(Record):
    """Một lần cấp/thu hồi quyền – chỉ thêm (đặc tả 04 mục 2.2)."""

    staff_id: str
    kind: str                              # level | capability
    key: str                               # 'level' hoặc vd 'ai.send_unedited'
    value: Any
    effective_from: str = Field(default_factory=_now)
    effective_to: Optional[str] = None
    reason: str = ''
    granted_by: str = ''
    source: str = 'admin_api'              # settings_page | quick_popup | agent_proposal | admin_api


class StaffPresence(Record):
    staff_id: str
    status: str                            # offline | online | away
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


class AiSuggestion(Record):
    conversation_id: str
    for_message_id: Optional[str] = None
    staff_id: Optional[str] = None
    staff_level: str = 'C1'
    agent_id: str
    prompt_version: Optional[int] = None
    model: str = ''
    status: str = 'ready'                  # ready | error
    error: Optional[str] = None
    reply_draft: str = ''
    follow_up_questions: list[str] = Field(default_factory=list)
    internal_notes: str = ''
    sources: list[dict[str, Any]] = Field(default_factory=list)
    scope_check: dict[str, Any] = Field(default_factory=dict)
    red_flags: list[str] = Field(default_factory=list)
    monitoring_advice: str = ''
    appointment_needed: Optional[bool] = None
    confidence: str = ''
    regenerate_instruction: Optional[str] = None
    outcome: Optional[str] = None          # sent_unedited | edited | discarded | superseded
    final_message_id: Optional[str] = None
    edit_ratio: Optional[float] = None
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


class GuardCheck(Record):
    conversation_id: str
    staff_id: str
    staff_level: str
    text: str
    verdict: str                           # ok | warn | block
    issues: list[str] = Field(default_factory=list)
    explanation: str = ''
    hard_block: bool = False               # vd thuốc kê đơn: không cho gửi dù xác nhận
    llm_available: bool = True
    confirmed_reason: Optional[str] = None
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


# ---------- quản lý (P3) ----------

class ManagerSession(Record):
    manager_id: str
    title: str = 'Phiên làm việc'
    days: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=_now)


class ManagerMessage(Record):
    session_id: str
    role: str                              # user | assistant
    content: str = ''
    # Thẻ có cấu trúc kèm theo: form (markdown dựng bằng code), bảng, đề xuất thao tác
    cards: list[dict[str, Any]] = Field(default_factory=list)
    local_date: str = ''

    def model_post_init(self, _ctx):
        if not self.local_date:
            from backend.core import parse_iso
            self.local_date = local_date(parse_iso(self.created_at))


class ActionProposal(Record):
    """Thao tác ghi do AG-7 đề xuất – chỉ thực hiện khi quản lý bấm Xác nhận (D-6)."""

    session_id: Optional[str] = None
    manager_id: str
    kind: str                              # permission | assignment
    payload: dict[str, Any]
    summary: str = ''
    before: dict[str, Any] = Field(default_factory=dict)
    reason: str = ''
    status: str = 'pending'                # pending | confirmed | cancelled | failed
    decided_at: Optional[str] = None
    result: Optional[str] = None
