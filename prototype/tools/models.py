"""Zhatura AI Customer Care — Tool Models (Phase 7).

Typed models for tool requests, data entities, caller identities, and tool results.
Never includes raw credentials or secrets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CallerRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    COACH = "coach"
    ACADEMY_ADMIN = "academy_admin"
    SUPPORT_ADMIN = "support_admin"
    UNKNOWN = "unknown"


class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    IDENTITY_COLLECTED = "IDENTITY_COLLECTED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass
class CallerIdentity:
    """Represents the authenticated caller identity for a specific call session."""
    caller_id: str
    phone: str = ""
    role: CallerRole = CallerRole.UNKNOWN
    auth_state: VerificationState = VerificationState.UNVERIFIED
    account_id: str | None = None
    student_id: str | None = None
    coach_id: str | None = None
    org_id: str | None = None
    name: str = ""
    children: list[str] = field(default_factory=list)
    assigned_students: list[str] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        return self.auth_state == VerificationState.VERIFIED


@dataclass
class AccountProfile:
    account_id: str
    role: CallerRole
    name: str
    status: str = "active"
    email: str = ""
    phone: str = ""
    created_at: str = ""
    children: list[str] = field(default_factory=list)
    assigned_students: list[str] = field(default_factory=list)
    org_id: str | None = None
    org_name: str | None = None


@dataclass
class StudentProfile:
    student_id: str
    account_id: str
    name: str
    parent_account_id: str | None = None
    coach_id: str | None = None
    level: str = "Beginner"
    rating: int = 1000
    status: str = "active"


@dataclass
class ParentProfile:
    account_id: str
    name: str
    children: list[str] = field(default_factory=list)


@dataclass
class CoachProfile:
    coach_id: str
    account_id: str
    name: str
    assigned_students: list[str] = field(default_factory=list)
    org_id: str | None = None


@dataclass
class SessionInfo:
    session_id: str
    student_id: str
    title: str
    start_time: str
    status: str  # "scheduled", "in_progress", "completed", "unavailable", "cancelled"
    reason_if_unavailable: str | None = None
    coach_id: str | None = None


@dataclass
class SubscriptionInfo:
    account_id: str
    plan_id: str
    plan_name: str
    status: str  # "active", "expired", "cancelled", "trial"
    billing_cycle: str = "monthly"
    renewal_date: str = ""


@dataclass
class SupportTicket:
    ticket_id: str
    account_id: str | None
    caller_id: str
    issue_category: str
    summary: str
    conversation_summary: str
    language: str
    priority: str = "normal"
    source: str = "voice_ai"
    status: str = "open"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass
class CallbackRequest:
    request_id: str
    caller_id: str
    account_id: str | None
    reason: str
    preferred_language: str
    preferred_window: str = "earliest_available"
    status: str = "pending"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass
class FeedbackRecord:
    feedback_id: str
    caller_id: str
    account_id: str | None
    text: str
    category: str
    language: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass
class LeadRecord:
    lead_id: str
    lead_type: str  # "academy", "custom_plan"
    organization_name: str
    contact_info: str
    student_count: int | None
    summary: str
    preferred_language: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass
class EscalationSummary:
    caller_role: str
    verification_status: str
    issue: str
    attempted_steps: list[str]
    relevant_tool_results: list[dict]
    unresolved_reason: str
    language: str
    urgency: str = "medium"
    ticket_id: str | None = None
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))


@dataclass
class ToolResult:
    """Standard output envelope for all tool calls."""
    success: bool
    verified: bool
    source: str
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    data: Any = None
    error_code: str | None = None
    safe_message: str = ""
    internal_metadata: dict = field(default_factory=dict)


@dataclass
class ToolCall:
    """Encapsulates a request to invoke a specific tool."""
    tool_name: str
    arguments: dict = field(default_factory=dict)
    caller_identity: CallerIdentity | None = None
    idempotency_key: str | None = None
