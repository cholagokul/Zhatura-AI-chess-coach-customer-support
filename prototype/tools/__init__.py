"""Zhatura AI Customer Care — Tools Package (Phase 7).

Public interface for customer account tools, permissions, support actions,
and tool registry.
"""

from .errors import (
    BackendNotConfiguredError,
    BackendUnavailableError,
    NotAuthorizedError,
    NotFoundError,
    NotVerifiedError,
    ToolError,
    ToolTimeoutError,
)
from .models import (
    AccountProfile,
    CallbackRequest,
    CallerIdentity,
    CallerRole,
    CoachProfile,
    EscalationSummary,
    FeedbackRecord,
    LeadRecord,
    ParentProfile,
    SessionInfo,
    StudentProfile,
    SubscriptionInfo,
    SupportTicket,
    ToolCall,
    ToolResult,
    VerificationState,
)
from .permissions import PermissionService
from .registry import ToolDefinition, ToolRegistry, create_default_registry
from .service import SupportToolService

__all__ = [
    "SupportToolService",
    "PermissionService",
    "ToolRegistry",
    "ToolDefinition",
    "create_default_registry",
    "CallerRole",
    "VerificationState",
    "CallerIdentity",
    "AccountProfile",
    "StudentProfile",
    "ParentProfile",
    "CoachProfile",
    "SessionInfo",
    "SubscriptionInfo",
    "SupportTicket",
    "CallbackRequest",
    "FeedbackRecord",
    "LeadRecord",
    "EscalationSummary",
    "ToolResult",
    "ToolCall",
    "ToolError",
    "BackendUnavailableError",
    "BackendNotConfiguredError",
    "NotFoundError",
    "NotAuthorizedError",
    "NotVerifiedError",
    "ToolTimeoutError",
]
