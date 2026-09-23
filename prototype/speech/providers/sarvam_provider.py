"""Zhatura AI Customer Care — Phase 7.1 Sarvam Voice Provider.

Wraps existing RealtimeSTT and StreamingTTS under the unified VoiceProvider
interface. Handles Sarvam failure simulation modes and maps Indian language
capabilities.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from speech.realtime_stt import RealtimeSTT
from speech.streaming_tts import StreamingTTS
from speech.providers.base import (
    VoiceProvider,
    OnSpeechStart,
    OnSpeechEnd,
    OnPartial,
    OnFinal,
    OnError,
    OnAudioChunk,
)
from speech.providers.errors import (
    ProviderError,
    ProviderUnavailableError,
    ProviderQuotaExhaustedError,
    ProviderAuthError,
    ProviderRateLimitedError,
)
from agent.languages import supports_tts, supports_stt

logger = logging.getLogger(__name__)

MAX_STT_FRAME_BYTES = 16000


class SarvamProvider(VoiceProvider):
    """Voice provider implementation for Sarvam AI (saaras:v4 STT + bulbul:v3 TTS)."""

    def __init__(self, cfg=None, client=None, fail_mode: str | None = None, stt_cls=None, tts_cls=None):
        self.cfg = cfg
        self._client = client
        if fail_mode is not None:
            self.fail_mode = fail_mode
        else:
            self.fail_mode = getattr(cfg, "sarvam_fail_mode", "none") or "none"
        real_stt_cls = stt_cls or RealtimeSTT
        real_tts_cls = tts_cls or StreamingTTS
        self._stt = real_stt_cls(cfg=cfg, client=client)
        self._tts = real_tts_cls(cfg=cfg, client=getattr(self._stt, "_client", client))
        self._started = False

    @property
    def name(self) -> str:
        return "sarvam"

    @property
    def stt(self) -> RealtimeSTT:
        return self._stt

    @property
    def tts(self) -> StreamingTTS:
        return self._tts

    def wire_stt_callbacks(
        self,
        *,
        on_speech_start: OnSpeechStart | None = None,
        on_speech_end: OnSpeechEnd | None = None,
        on_partial: OnPartial | None = None,
        on_final: OnFinal | None = None,
        on_error: OnError | None = None,
    ) -> None:
        if on_speech_start is not None:
            self._stt.on_speech_start = on_speech_start
        if on_speech_end is not None:
            self._stt.on_speech_end = on_speech_end
        if on_partial is not None:
            self._stt.on_partial = on_partial
        if on_final is not None:
            self._stt.on_final = on_final
        if on_error is not None:
            self._stt.on_error = on_error

    def _check_simulation(self, component: str) -> None:
        """Check if simulated failure is triggered."""
        mode = self.fail_mode.lower()
        if mode in ("none", ""):
            return
        if mode in ("quota", "auth", "ratelimit") or mode in ("both", component) or (component in ("stt", "tts") and mode == "all"):
            logger.warning("[SarvamProvider] Triggering simulated failure (mode=%s, component=%s)", mode, component)
            if mode == "quota":
                raise ProviderQuotaExhaustedError("Sarvam account quota exhausted (simulated 402)", provider="sarvam", status_code=402)
            elif mode == "auth":
                raise ProviderAuthError("Sarvam API key invalid (simulated 401)", provider="sarvam", status_code=401)
            elif mode == "ratelimit":
                raise ProviderRateLimitedError("Sarvam rate limit exceeded (simulated 429)", provider="sarvam", status_code=429)
            raise ProviderUnavailableError(f"Sarvam {component.upper()} unavailable (simulated)", provider="sarvam")

    async def start(self, tts_language: str = "en-IN") -> None:
        self._check_simulation("connect")
        self._check_simulation("stt")
        await self._stt.start()
        self._check_simulation("tts")
        await self._tts.open(tts_language)
        self._started = True
        logger.info("[SarvamProvider] STT and TTS services started.")

    async def stop(self) -> None:
        self._started = False
        try:
            await self._stt.stop()
        except Exception as exc:
            logger.debug("[SarvamProvider] Error stopping STT: %s", exc)
        try:
            await self._tts.close()
        except Exception as exc:
            logger.debug("[SarvamProvider] Error closing TTS: %s", exc)
        logger.info("[SarvamProvider] Stopped.")

    async def send_audio(self, pcm_bytes: bytes) -> None:
        self._check_simulation("stt")
        for i in range(0, len(pcm_bytes), MAX_STT_FRAME_BYTES):
            await self._stt.send_audio(pcm_bytes[i : i + MAX_STT_FRAME_BYTES])

    async def synthesize(
        self, text: str, language_code: str, on_audio_chunk: OnAudioChunk
    ) -> None:
        self._check_simulation("tts")
        await self._tts.synthesize(text, language_code, on_audio_chunk)

    def supports_tts_language(self, language_code: str) -> bool:
        return supports_tts(language_code)

    def supports_stt_language(self, language_code: str) -> bool:
        return supports_stt(language_code)

    def map_tts_language(self, language_code: str, fallback: str = "en-IN") -> str:
        if self.supports_tts_language(language_code):
            return language_code
        return fallback
