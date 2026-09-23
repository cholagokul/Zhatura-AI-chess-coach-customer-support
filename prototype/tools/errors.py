"""Zhatura AI Customer Care — Tool Error Taxonomy (Phase 7).

Structured exceptions for tool calls. Messages are safe to inspect and
never expose private credentials, tokens, or raw system traces.
"""

from __future__ import annotations


class ToolError(Exception):
    """Base exception for all tool operations."""
    code: str = "INTERNAL_ERROR"
    safe_message: str = "A system error occurred while processing your request."

    def __init__(self, message: str | None = None, code: str | None = None, safe_message: str | None = None):
        super().__init__(message or self.safe_message)
        if code:
            self.code = code
        if safe_message:
            self.safe_message = safe_message


class BackendUnavailableError(ToolError):
    """Raised when the backend service is offline, unreachable, or returns 5xx."""
    code = "BACKEND_UNAVAILABLE"
    safe_message = "I cannot access the account system right now. Please try again in a few moments."


class BackendNotConfiguredError(ToolError):
    """Raised when a real backend adapter is invoked without configuration or credentials."""
    code = "BACKEND_NOT_CONFIGURED"
    safe_message = "The requested account backend integration is not currently configured."


class NotFoundError(ToolError):
    """Raised when the requested entity (account, student, session) is not found."""
    code = "NOT_FOUND"
    safe_message = "The requested record could not be found."


class NotAuthorizedError(ToolError):
    """Raised when caller lacks permission to perform the action or view the data."""
    code = "NOT_AUTHORIZED"
    safe_message = "You do not have permission to access these details."


class NotVerifiedError(ToolError):
    """Raised when an operation requires verification but the caller is unverified."""
    code = "NOT_VERIFIED"
    safe_message = "I need to verify your account before accessing those details."


class InvalidRequestError(ToolError):
    """Raised when tool arguments are malformed or missing required fields."""
    code = "INVALID_REQUEST"
    safe_message = "The request was missing required details."


class ToolTimeoutError(ToolError):
    """Raised when a tool operation exceeds its allotted deadline."""
    code = "TIMEOUT"
    safe_message = "The system took too long to respond. Please try again."


class RateLimitedError(ToolError):
    """Raised when tool call frequency limits are exceeded."""
    code = "RATE_LIMITED"
    safe_message = "The system is currently busy. Please try again shortly."
