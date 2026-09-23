"""Zhatura AI Customer Care — Phase 7.1 Provider Health & Circuit Breaker.

Tracks operational health, consecutive failure counts, and cooldown windows
for speech providers. Prevents hammering failing endpoints and manages automatic
circuit breaking.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class ProviderHealthState:
    """Runtime health metrics and cooldown tracking for a single provider."""

    provider: str
    failure_count: int = 0
    success_count: int = 0
    last_failure_reason: str = ""
    last_failure_time: float = 0.0
    cooldown_until: float = 0.0
    is_circuit_open: bool = False
    is_configured: bool = True

    def is_available(self, now: float | None = None) -> bool:
        """Returns True if the provider is healthy or cooldown has expired."""
        if not self.is_configured:
            return False
        if now is None:
            now = time.monotonic()
        if self.is_circuit_open:
            if now >= self.cooldown_until:
                # Cooldown period expired, allow probe
                return True
            return False
        return True

    def to_dict(self, now: float | None = None) -> dict:
        if now is None:
            now = time.monotonic()
        cooldown_remaining = max(0.0, self.cooldown_until - now) if self.is_circuit_open else 0.0
        if not self.is_configured:
            status = "unavailable"
        elif self.is_circuit_open and cooldown_remaining > 0:
            status = "unhealthy"
        else:
            status = "healthy"
        d = {
            "status": status,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_reason": self.last_failure_reason,
            "circuit_open": self.is_circuit_open,
            "cooldown_remaining_seconds": round(cooldown_remaining, 1),
        }
        if not self.is_configured and self.last_failure_reason:
            d["reason"] = self.last_failure_reason
        return d


class ProviderHealthManager:
    """Central registry tracking voice provider health and circuit breaking."""

    def __init__(self, default_cooldown_seconds: float = 300.0):
        self.default_cooldown_seconds = default_cooldown_seconds
        self._states: Dict[str, ProviderHealthState] = {
            "sarvam": ProviderHealthState(provider="sarvam"),
            "elevenlabs": ProviderHealthState(provider="elevenlabs"),
        }

    def _get_state(self, provider: str) -> ProviderHealthState:
        if provider not in self._states:
            self._states[provider] = ProviderHealthState(provider=provider)
        return self._states[provider]

    def is_healthy(self, provider: str) -> bool:
        """Check if provider is eligible to accept calls or handle turns."""
        state = self._get_state(provider)
        return state.is_available()

    def set_unavailable(self, provider: str, reason: str = "missing_api_key") -> None:
        """Explicitly mark a provider as unavailable (e.g. missing API key)."""
        state = self._get_state(provider)
        state.is_configured = False
        state.last_failure_reason = reason
        logger.info("Provider [%s] marked unavailable: %s", provider, reason)

    def record_success(self, provider: str) -> None:
        """Record a successful operation (e.g. turn completed). Resets circuit."""
        state = self._get_state(provider)
        state.is_configured = True
        state.success_count += 1
        if state.is_circuit_open and time.monotonic() >= state.cooldown_until:
            # Successfully recovered after cooldown
            state.is_circuit_open = False
            state.failure_count = 0
            state.last_failure_reason = ""
            logger.info("Provider [%s] successfully probed and circuit reset to HEALTHY.", provider)

    def record_failure(
        self,
        provider: str,
        reason: str,
        cooldown_seconds: float | None = None,
        hard_break: bool = True,
    ) -> None:
        """Record a failure event. Trips circuit breaker and enforces cooldown."""
        state = self._get_state(provider)
        state.failure_count += 1
        state.last_failure_reason = reason
        now = time.monotonic()
        state.last_failure_time = now

        cooldown = cooldown_seconds if cooldown_seconds is not None else self.default_cooldown_seconds
        if hard_break or state.failure_count >= 2:
            state.is_circuit_open = True
            state.cooldown_until = now + cooldown
            logger.warning(
                "Provider [%s] tripped CIRCUIT BREAKER (reason: %s). Cooldown for %ss.",
                provider,
                reason,
                cooldown,
            )
        else:
            logger.warning("Provider [%s] failure #%d: %s", provider, state.failure_count, reason)

    def reset(self, provider: str | None = None) -> None:
        """Reset circuit breaker and failure counts."""
        if provider is not None:
            self._states[provider] = ProviderHealthState(provider=provider)
            logger.info("Provider [%s] health state reset.", provider)
        else:
            for p in list(self._states.keys()):
                self._states[p] = ProviderHealthState(provider=p)
            logger.info("All provider health states reset.")

    def get_status_report(self) -> dict:
        """Return safe status dictionary for health endpoints and diagnostics."""
        now = time.monotonic()
        return {p: state.to_dict(now) for p, state in self._states.items()}
