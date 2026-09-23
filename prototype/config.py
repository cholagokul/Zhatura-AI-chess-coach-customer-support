"""Zhatura AI Customer Care — Phase 1 configuration.

Loads configuration from the project ``.env`` file using ``python-dotenv``
and validates the required settings. Secret values are never printed,
logged, or included in error messages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the `prototype/` package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Validated application configuration.

    ``sarvam_api_key`` is write-only in practice: it must never be
    printed, logged, or included in exceptions.
    """

    sarvam_api_key: str
    env_file_found: bool
    # Phase 2 — Sarvam speech settings (safe defaults; overridable via .env)
    tts_model: str = "bulbul:v3"
    tts_language: str = "en-IN"
    tts_speaker: str = "shreya"
    tts_sample_rate: int = 24000
    stt_model: str = "saaras:v4"
    stt_language: str = "en-IN"
    stt_mode: str = "transcribe"
    # Phase 3 — realtime conversation settings
    realtime_stt_model: str = "saaras:v4"
    realtime_stt_language: str = "auto"
    realtime_stt_stream_type: str = "fast"
    stt_prompt: str = (
        "Zhatura, Zhatura AI, Zhatura AI Chess Coach, AI Chess Coach, "
        "Student Dashboard, Parent Dashboard, Coach Dashboard, "
        "Chess Academy, Chess Coach"
    )
    stt_vad_threshold: float = 0.3
    stt_silence_duration_ms: int = 500
    stt_min_speech_duration_ms: int = 250
    chat_model: str = "sarvam-105b-conversations"
    chat_max_tokens: int = 150
    microphone_sample_rate: int = 16000
    tts_stream_sample_rate: int = 22050
    auto_greeting: bool = True
    silence_timeout_seconds: int = 20
    max_conversation_turns: int = 20
    # Phase 4 — Exotel telephony settings (no Exotel credentials needed
    # for the inbound Voicebot flow; stream identifiers arrive over the
    # WebSocket itself).
    exotel_ws_host: str = "0.0.0.0"
    exotel_ws_port: int = 8000
    exotel_ws_path: str = "/ws"
    exotel_audio_sample_rate: int = 16000
    exotel_phone_number: str = ""   # operational reference only
    # Phase 4.1 — multilingual settings. STT detects all scheduled
    # Sarvam languages; Bulbul v3 TTS covers only a subset. For
    # TTS-unsupported languages the session applies this policy; it
    # never silently synthesizes the wrong language.
    tts_fallback_policy: str = "ask_hi_en"   # ask_hi_en | secondary_later
    tts_fallback_language: str = "en-IN"     # spoken fallback voice
    # Phase 5 — verified Zhatura knowledge base. Grounded answers only:
    # retrieval runs locally over knowledge/sources/; the LLM is
    # instructed to answer only from retrieved context and to admit
    # gaps instead of inventing plan/pricing/account facts.
    knowledge_enabled: bool = True
    knowledge_dir: str = ""   # default: prototype/knowledge/sources
    # Phase 7 — real account tools + support actions settings
    support_backend_mode: str = "mock"       # mock | real | disabled
    mock_verification_enabled: bool = True
    accounts_fixture_path: str = ""
    # Phase 7.1 — dual voice provider failover settings
    voice_primary_provider: str = "sarvam"
    voice_secondary_provider: str = "elevenlabs"
    provider_health_cooldown_seconds: int = 300
    max_provider_failovers_per_call: int = 1
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    elevenlabs_stt_model_id: str = "scribe_v1"
    sarvam_fail_mode: str = "none"
    elevenlabs_fail_mode: str = "none"


def load_config() -> Config:
    """Load ``.env`` and return validated configuration.

    Raises:
        ConfigurationError: if ``SARVAM_API_KEY`` is missing or empty.
            The error message never contains any secret value.
    """
    env_file_found = ENV_FILE.is_file()
    # load_dotenv does not override variables already set in the environment.
    load_dotenv(ENV_FILE)

    api_key = (os.environ.get("SARVAM_API_KEY") or "").strip()
    if not api_key:
        raise ConfigurationError(
            "Configuration error:\n"
            "SARVAM_API_KEY is not configured.\n\n"
            "Add it to the project .env file at:\n"
            f"  {ENV_FILE}\n\n"
            "See .env.example for the expected format."
        )

    def _env(name: str, default: str) -> str:
        value = (os.environ.get(name) or "").strip()
        return value or default

    def _env_int(name: str, default: int) -> int:
        raw = _env(name, "")
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ConfigurationError(
                f"Configuration error:\n{name} must be an integer (got non-numeric value)."
            ) from None

    def _env_float(name: str, default: float) -> float:
        raw = _env(name, "")
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            raise ConfigurationError(
                f"Configuration error:\n{name} must be a number (got non-numeric value)."
            ) from None

    def _env_bool(name: str, default: bool) -> bool:
        raw = _env(name, "").lower()
        if not raw:
            return default
        return raw in ("1", "true", "yes", "on")

    sample_rate = _env_int("SARVAM_TTS_SAMPLE_RATE", 24000)

    return Config(
        sarvam_api_key=api_key,
        env_file_found=env_file_found,
        tts_model=_env("SARVAM_TTS_MODEL", "bulbul:v3"),
        tts_language=_env("SARVAM_TTS_LANGUAGE", "en-IN"),
        tts_speaker=_env("SARVAM_TTS_SPEAKER", "shreya"),
        tts_sample_rate=sample_rate,
        stt_model=_env("SARVAM_STT_MODEL", "saaras:v4"),
        stt_language=_env("SARVAM_STT_LANGUAGE", "en-IN"),
        stt_mode=_env("SARVAM_STT_MODE", "transcribe"),
        realtime_stt_model=_env("SARVAM_REALTIME_STT_MODEL", "saaras:v4"),
        realtime_stt_language=_env("SARVAM_STT_REALTIME_LANGUAGE", "auto"),
        realtime_stt_stream_type=_env("SARVAM_STT_STREAM_TYPE", "fast"),
        stt_prompt=_env(
            "SARVAM_STT_PROMPT",
            "Zhatura, Zhatura AI, Zhatura AI Chess Coach, AI Chess Coach, "
            "Student Dashboard, Parent Dashboard, Coach Dashboard, "
            "Chess Academy, Chess Coach",
        ),
        stt_vad_threshold=_env_float("STT_VAD_THRESHOLD", 0.3),
        stt_silence_duration_ms=_env_int("STT_SILENCE_DURATION_MS", 500),
        stt_min_speech_duration_ms=_env_int("STT_MIN_SPEECH_DURATION_MS", 250),
        chat_model=_env("SARVAM_CHAT_MODEL", "sarvam-105b-conversations"),
        chat_max_tokens=_env_int("SARVAM_CHAT_MAX_TOKENS", 150),
        microphone_sample_rate=_env_int("MICROPHONE_SAMPLE_RATE", 16000),
        tts_stream_sample_rate=_env_int("SARVAM_TTS_STREAM_SAMPLE_RATE", 22050),
        auto_greeting=_env_bool("AUTO_GREETING", True),
        silence_timeout_seconds=_env_int("CONVERSATION_SILENCE_TIMEOUT_SECONDS", 20),
        max_conversation_turns=_env_int("MAX_CONVERSATION_TURNS", 20),
        exotel_ws_host=_env("EXOTEL_WEBSOCKET_HOST", "0.0.0.0"),
        exotel_ws_port=_env_int("EXOTEL_WEBSOCKET_PORT", 8000),
        exotel_ws_path=_env("EXOTEL_WEBSOCKET_PATH", "/ws"),
        exotel_audio_sample_rate=_env_int("EXOTEL_AUDIO_SAMPLE_RATE", 16000),
        exotel_phone_number=_env("EXOTEL_PHONE_NUMBER", ""),
        tts_fallback_policy=_env("TTS_FALLBACK_POLICY", "ask_hi_en"),
        tts_fallback_language=_env("TTS_FALLBACK_LANGUAGE", "en-IN"),
        knowledge_enabled=_env_bool("KNOWLEDGE_ENABLED", True),
        knowledge_dir=_env("KNOWLEDGE_DIR", ""),
        support_backend_mode=_env("SUPPORT_BACKEND_MODE", "mock"),
        mock_verification_enabled=_env_bool("MOCK_VERIFICATION_ENABLED", True),
        accounts_fixture_path=_env("ACCOUNTS_FIXTURE_PATH", ""),
        voice_primary_provider=_env("VOICE_PRIMARY_PROVIDER", "sarvam").lower(),
        voice_secondary_provider=_env("VOICE_SECONDARY_PROVIDER", "elevenlabs").lower(),
        provider_health_cooldown_seconds=_env_int("PROVIDER_HEALTH_COOLDOWN_SECONDS", 300),
        max_provider_failovers_per_call=_env_int("MAX_PROVIDER_FAILOVERS_PER_CALL", 1),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY", ""),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        elevenlabs_model_id=_env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
        elevenlabs_stt_model_id=_env("ELEVENLABS_STT_MODEL_ID", "scribe_v1"),
        sarvam_fail_mode=_env("SARVAM_FAIL_MODE", "none").lower(),
        elevenlabs_fail_mode=_env("ELEVENLABS_FAIL_MODE", "none").lower(),
    )
