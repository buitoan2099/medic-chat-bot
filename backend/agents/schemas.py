"""Lược đồ đầu ra có cấu trúc của các agent (đặc tả 03 mục 1.4)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScopeCheck(BaseModel):
    status: Literal['within', 'exceeds']
    suggested_level: Optional[Literal['C1', 'C2', 'C3']] = None
    reason: str = ''


class CopilotOutput(BaseModel):
    """AG-2..4 (đặc tả 03 mục 4.1). `sources` do hệ thống điền từ kết quả tra cứu."""

    reply_draft: str
    follow_up_questions: list[str] = Field(default_factory=list)
    internal_notes: str = ''
    scope_check: ScopeCheck
    red_flags: list[str] = Field(default_factory=list)
    monitoring_advice: str = ''
    appointment_needed: Optional[bool] = None
    confidence: Literal['high', 'medium', 'low'] = 'medium'
    confidence_reason: str = ''


class ProfileUpdate(BaseModel):
    age: Optional[str] = None
    sex: Optional[str] = None
    pregnant_or_breastfeeding: Optional[str] = None
    allergies: Optional[str] = None
    conditions: Optional[str] = None
    current_medications: Optional[str] = None
    chief_complaint: Optional[str] = None
    onset: Optional[str] = None
    severity: Optional[str] = None


class CaseMemoryOutput(BaseModel):
    """AG-5 (đặc tả 03 mục 5)."""

    profile: ProfileUpdate
    needs_confirmation: list[str] = Field(default_factory=list)
    summary: str = ''


GuardIssue = Literal['exceeds_level', 'prescription_drug', 'specific_dose_without_level',
                     'otc_not_in_list', 'missing_max_duration', 'missing_monitoring_advice',
                     'citation_leak', 'contraindication_risk', 'emergency_not_addressed']


class GuardOutput(BaseModel):
    """AG-6 (đặc tả 03 mục 6)."""

    verdict: Literal['ok', 'warn', 'block']
    issues: list[GuardIssue] = Field(default_factory=list)
    explanation: str = ''
