"""Zhatura AI Customer Care — Dual Voice Providers Package (Phase 7.1)."""

from speech.providers.base import VoiceProvider
from speech.providers.errors import (
    AllProvidersUnavailableError,
    FailoverLimitExceededError,
    ProviderAudioFormatError,
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from speech.providers.health import ProviderHealthManager, ProviderHealthState
from speech.providers.sarvam_provider import SarvamProvider
from speech.providers.elevenlabs_provider import ElevenLabsProvider
from speech.providers.manager import VoiceProviderManager
from speech.providers.emergency_audio import (
    EMERGENCY_MESSAGE_TEXT,
    get_emergency_audio_pcm,
)

__all__ = [
    "VoiceProvider",
    "SarvamProvider",
    "ElevenLabsProvider",
    "VoiceProviderManager",
    "ProviderHealthManager",
    "ProviderHealthState",
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderQuotaExhaustedError",
    "ProviderAuthError",
    "ProviderRateLimitedError",
    "ProviderTimeoutError",
    "ProviderAudioFormatError",
    "FailoverLimitExceededError",
    "AllProvidersUnavailableError",
    "get_emergency_audio_pcm",
    "EMERGENCY_MESSAGE_TEXT",
]
