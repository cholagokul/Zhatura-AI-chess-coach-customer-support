"""Zhatura AI Customer Care — Phase 7.1 Voice Provider Errors.

Defines exception types for voice provider failures, circuit breakers,
and failover coordination.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all voice provider errors."""

    def __init__(self, message: str, provider: str = "", status_code: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class ProviderUnavailableError(ProviderError):
    """Provider network endpoint is unreachable or down."""


class ProviderQuotaExhaustedError(ProviderError):
    """Provider account has exhausted credits or quota (HTTP 402)."""


class ProviderAuthError(ProviderError):
    """Provider authentication failed (HTTP 401/403). Check API keys."""


class ProviderRateLimitedError(ProviderError):
    """Provider rejected requests due to rate limiting (HTTP 429)."""


class ProviderTimeoutError(ProviderError):
    """Provider request or stream timed out."""


class ProviderAudioFormatError(ProviderError):
    """Audio format or sample rate is unsupported by provider."""


class FailoverLimitExceededError(ProviderError):
    """Call has already executed maximum allowed failovers (no ping-pong)."""


class AllProvidersUnavailableError(ProviderError):
    """Both primary and secondary providers are unhealthy or failed."""
