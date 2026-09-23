"""Zhatura AI Customer Care — Tool Audit Logging (Phase 7).

Structured, PII-safe audit logging for all tool interactions.
Never logs passwords, OTPs, full phone numbers, full emails, or raw secret payloads.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("tools.audit")

_PHONE_RE = re.compile(r"(\+?\d{1,3}[-.\s]?)?(\d{2})\d{4,6}(\d{2,4})")
_EMAIL_RE = re.compile(r"([^@\s]{1,2})[^@\s]+@([^\s@]+)")


def mask_phone(phone: str | None) -> str:
    """Mask phone number preserving only country code hint and trailing digits."""
    if not phone:
        return ""
    clean = phone.strip()
    if len(clean) < 6:
        return "***"
    return f"{clean[:4]}****{clean[-4:]}"


def mask_email(email: str | None) -> str:
    """Mask email address preserving initial char and domain."""
    if not email or "@" not in email:
        return ""
    parts = email.split("@", 1)
    user = parts[0]
    domain = parts[1]
    masked_user = f"{user[:2]}***" if len(user) > 2 else f"{user[0]}***"
    return f"{masked_user}@{domain}"


def mask_identifier(ident: str | None) -> str:
    """Safely mask internal or secret identifiers."""
    if not ident:
        return ""
    if len(ident) <= 4:
        return "***"
    return f"{ident[:3]}***{ident[-2:]}"


def log_tool_audit(
    tool_name: str,
    caller_verified: bool,
    role: str,
    result: str,  # "success", "denied", "error", "timeout"
    latency_ms: int,
    caller_id: str | None = None,
    account_id: str | None = None,
    error_code: str | None = None,
) -> None:
    """Emit a single-line structured audit record without sensitive payloads."""
    masked_caller = mask_identifier(caller_id) if caller_id else "anon"
    masked_account = mask_identifier(account_id) if account_id else "none"
    err_suffix = f" error={error_code}" if error_code else ""
    logger.info(
        "TOOL_CALL tool=%s caller_verified=%s role=%s result=%s latency_ms=%d caller=%s account=%s%s",
        tool_name,
        caller_verified,
        role,
        result,
        latency_ms,
        masked_caller,
        masked_account,
        err_suffix,
    )
