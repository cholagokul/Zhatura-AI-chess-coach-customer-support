"""Zhatura AI Customer Care — Phase 7.1 Voice Provider Manager.

Coordinates provider health evaluation, call-start provider selection,
and in-call atomic failover between Sarvam and ElevenLabs. Enforces per-call
locking and prevents ping-pong provider switching.
"""

from __future__ import annotations

import logging
from typing import Any, Tuple

from speech.providers.base import VoiceProvider
from speech.providers.errors import (
    AllProvidersUnavailableError,
    FailoverLimitExceededError,
    ProviderError,
)
from speech.providers.health import ProviderHealthManager
from speech.providers.sarvam_provider import SarvamProvider
from speech.providers.elevenlabs_provider import ElevenLabsProvider

logger = logging.getLogger(__name__)


class VoiceProviderManager:
    """Manages lifecycle and failover of dual voice providers."""

    def __init__(
        self,
        cfg=None,
        sarvam_client=None,
        health_manager: ProviderHealthManager | None = None,
    ):
        self.cfg = cfg
        self._sarvam_client = sarvam_client
        cooldown = getattr(cfg, "provider_health_cooldown_seconds", 300) if cfg else 300
        self.health_manager = health_manager or ProviderHealthManager(
            default_cooldown_seconds=cooldown
        )
        self.primary_name = getattr(cfg, "voice_primary_provider", "sarvam") or "sarvam"
        self.secondary_name = getattr(cfg, "voice_secondary_provider", "elevenlabs") or "elevenlabs"
        self.max_failovers_per_call = getattr(cfg, "max_provider_failovers_per_call", 1) or 1

    def create_provider(
        self, name: str, stt_cls=None, tts_cls=None
    ) -> VoiceProvider:
        """Instantiate a VoiceProvider by name."""
        name_lower = name.lower()
        if name_lower == "sarvam":
            return SarvamProvider(
                cfg=self.cfg,
                client=self._sarvam_client,
                stt_cls=stt_cls,
                tts_cls=tts_cls,
            )
        elif name_lower == "elevenlabs":
            return ElevenLabsProvider(cfg=self.cfg)
        raise ValueError(f"Unknown voice provider: '{name}'")

    def select_initial_provider(
        self, stt_cls=None, tts_cls=None
    ) -> Tuple[VoiceProvider, str]:
        """Select the healthy provider at call initiation.

        Returns (provider_instance, provider_name).
        Prefers primary_name; if unhealthy, falls back to secondary_name.
        Raises AllProvidersUnavailableError if neither is healthy.
        """
        primary_healthy = self.health_manager.is_healthy(self.primary_name)
        secondary_healthy = self.health_manager.is_healthy(self.secondary_name)

        if primary_healthy:
            logger.info(
                "Call starting on PRIMARY provider: %s", self.primary_name
            )
            return (
                self.create_provider(
                    self.primary_name, stt_cls=stt_cls, tts_cls=tts_cls
                ),
                self.primary_name,
            )

        if secondary_healthy:
            logger.warning(
                "Primary provider [%s] is UNHEALTHY. Starting call on SECONDARY: %s",
                self.primary_name,
                self.secondary_name,
            )
            return (
                self.create_provider(
                    self.secondary_name, stt_cls=stt_cls, tts_cls=tts_cls
                ),
                self.secondary_name,
            )

        logger.critical(
            "ALL voice providers are UNHEALTHY (primary=%s, secondary=%s)!",
            self.primary_name,
            self.secondary_name,
        )
        raise AllProvidersUnavailableError(
            f"Neither {self.primary_name} nor {self.secondary_name} is currently available"
        )

    def get_failover_candidate(
        self, current_name: str, failover_count: int, stt_cls=None, tts_cls=None
    ) -> Tuple[VoiceProvider, str]:
        """Select the failover candidate for an active call.

        Enforces:
        1. failover_count < max_failovers_per_call (no ping-ponging).
        2. Candidate health check.

        Returns (new_provider_instance, new_provider_name).
        """
        if failover_count >= self.max_failovers_per_call:
            logger.error(
                "Call already reached maximum allowed failovers (%d/%d). Failing over disallowed.",
                failover_count,
                self.max_failovers_per_call,
            )
            raise FailoverLimitExceededError(
                f"Maximum allowed failovers ({self.max_failovers_per_call}) exceeded for this call."
            )

        target_name = (
            self.secondary_name
            if current_name == self.primary_name
            else self.primary_name
        )

        if not self.health_manager.is_healthy(target_name):
            logger.error(
                "Failover candidate [%s] is currently UNHEALTHY / in cooldown. Cannot failover.",
                target_name,
            )
            raise AllProvidersUnavailableError(
                f"Failover candidate {target_name} is unhealthy or in cooldown"
            )

        logger.warning(
            "FAILOVER APPROVED: %s -> %s (call failover count %d -> %d)",
            current_name,
            target_name,
            failover_count,
            failover_count + 1,
        )
        return (
            self.create_provider(
                target_name, stt_cls=stt_cls, tts_cls=tts_cls
            ),
            target_name,
        )

    def record_failure(self, provider_name: str, reason: str) -> None:
        """Mark provider failure and trigger circuit breaker cooldown."""
        self.health_manager.record_failure(provider_name, reason)

    def record_success(self, provider_name: str) -> None:
        """Mark provider success."""
        self.health_manager.record_success(provider_name)
