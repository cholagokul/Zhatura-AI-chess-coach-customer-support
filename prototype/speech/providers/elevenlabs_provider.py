"""Zhatura AI Customer Care — Phase 7.1 ElevenLabs Voice Provider.

Implements VoiceProvider using ElevenLabs APIs:
- Streaming TTS: POST /v1/text-to-speech/{voice_id}/stream (multilingual_v2)
- STT: Scribe / Speech-to-Text with VAD chunking and realtime speech endpointing

Supports simulated failure modes (ELEVENLABS_FAIL_MODE) for deterministic testing.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import struct
import time
import wave
from typing import Any, Awaitable, Callable

import httpx

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
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)

# Supported languages for ElevenLabs Multilingual models
ELEVENLABS_SUPPORTED_LANGUAGES = {
    "en", "en-IN", "en-US", "en-GB",
    "hi", "hi-IN",
    "ta", "ta-IN",
    "te", "te-IN",
    "kn", "kn-IN",
    "ml", "ml-IN",
    "mr", "mr-IN",
    "bn", "bn-IN",
    "gu", "gu-IN",
    "pa", "pa-IN",
    "ur", "ur-IN",
}

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Standard Rachel / multilingual voice
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


class ElevenLabsSTT:
    """Realtime STT adapter for ElevenLabs with audio buffering and VAD."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "scribe_v1",
        sample_rate: int = 16000,
        vad_threshold: float = 0.015,
        silence_timeout_ms: int = 600,
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.vad_threshold = vad_threshold
        self.silence_timeout_ms = silence_timeout_ms

        self.on_speech_start: OnSpeechStart = lambda: None
        self.on_speech_end: OnSpeechEnd = lambda: None
        self.on_partial: OnPartial = lambda _: None
        self.on_final: OnFinal = lambda _t, _l: None
        self.on_error: OnError = lambda _m: None

        self._audio_buffer = bytearray()
        self._is_speaking = False
        self._last_speech_time = 0.0
        self._silence_watchdog_task: asyncio.Task | None = None
        self._running = False
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._running = True
        self._client = httpx.AsyncClient(timeout=10.0)
        self._silence_watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("[ElevenLabsSTT] Started.")

    async def stop(self) -> None:
        self._running = False
        if self._silence_watchdog_task and not self._silence_watchdog_task.done():
            self._silence_watchdog_task.cancel()
            try:
                await self._silence_watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        self._audio_buffer.clear()
        self._is_speaking = False
        logger.info("[ElevenLabsSTT] Stopped.")

    def _calculate_rms(self, pcm_bytes: bytes) -> float:
        """Calculate RMS amplitude of 16-bit PCM bytes."""
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0
        sum_sq = 0.0
        for i in range(count):
            val = struct.unpack_from("<h", pcm_bytes, i * 2)[0] / 32768.0
            sum_sq += val * val
        return math.sqrt(sum_sq / count)

    async def send_audio(self, pcm_bytes: bytes) -> None:
        if not self._running:
            return
        rms = self._calculate_rms(pcm_bytes)
        now = time.monotonic()

        if rms >= self.vad_threshold:
            if not self._is_speaking:
                self._is_speaking = True
                self.on_speech_start()
            self._last_speech_time = now
            self._audio_buffer.extend(pcm_bytes)
        elif self._is_speaking:
            self._audio_buffer.extend(pcm_bytes)

    async def _watchdog(self) -> None:
        while self._running:
            await asyncio.sleep(0.05)
            if self._is_speaking:
                elapsed_ms = (time.monotonic() - self._last_speech_time) * 1000.0
                if elapsed_ms >= self.silence_timeout_ms:
                    # Speech endpoint reached
                    self._is_speaking = False
                    self.on_speech_end()
                    audio_to_transcribe = bytes(self._audio_buffer)
                    self._audio_buffer.clear()
                    asyncio.create_task(self._transcribe(audio_to_transcribe))

    async def _transcribe(self, audio_bytes: bytes) -> None:
        if len(audio_bytes) < 3200:  # Ignore under 100ms
            return
        if not self.api_key:
            # Without API key or in simulation, emit warning or error
            self.on_error("ElevenLabs API key missing for transcription")
            return

        # Package raw PCM into a standard WAV container
        wav_buf = io.BytesIO()
        try:
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_bytes)
            wav_payload = wav_buf.getvalue()
        except Exception as exc:
            logger.warning("[ElevenLabsSTT] Failed to format WAV payload: %s", exc)
            wav_payload = audio_bytes

        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": self.api_key}
        files = {"file": ("audio.wav", wav_payload, "audio/wav")}
        data = {"model_id": self.model_id}
        try:
            if self._client is None:
                return
            resp = await self._client.post(url, headers=headers, files=files, data=data)
            if resp.status_code == 200:
                result = resp.json()
                text = result.get("text", "").strip()
                lang = result.get("language_code", "en-IN")
                if text:
                    self.on_final(text, lang)
            elif resp.status_code in (401, 403):
                self.on_error("ElevenLabs authentication failure")
            elif resp.status_code == 402:
                self.on_error("ElevenLabs quota exhausted")
            elif resp.status_code == 429:
                self.on_error("ElevenLabs rate limit exceeded")
            else:
                self.on_error(f"ElevenLabs transcription error HTTP {resp.status_code}")
        except Exception as exc:
            self.on_error(f"ElevenLabs STT network error: {type(exc).__name__}")


class ElevenLabsTTS:
    """Streaming TTS implementation using ElevenLabs HTTP streaming."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
        sample_rate: int = 22050,
    ):
        self.api_key = api_key
        vid = (voice_id or DEFAULT_VOICE_ID).strip()
        if vid.lower() == "rachel":
            vid = DEFAULT_VOICE_ID
        self.voice_id = vid
        self.model_id = model_id or DEFAULT_MODEL_ID
        self.sample_rate = sample_rate
        self.is_open = False
        self.current_language = "en-IN"
        self._client: httpx.AsyncClient | None = None

    async def open(self, language_code: str = "en-IN") -> None:
        self.current_language = language_code
        self.is_open = True
        self._client = httpx.AsyncClient(timeout=15.0)
        logger.info("[ElevenLabsTTS] Opened (voice=%s, model=%s, lang=%s)", self.voice_id, self.model_id, language_code)

    async def close(self) -> None:
        self.is_open = False
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[ElevenLabsTTS] Closed.")

    async def synthesize(
        self, text: str, language_code: str, on_audio_chunk: OnAudioChunk
    ) -> None:
        """Stream MP3 audio chunks from ElevenLabs to on_audio_chunk."""
        if not text.strip():
            return
        if not self.api_key:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs", status_code=401)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        params = {"output_format": "mp3_44100_128"}

        client = self._client or httpx.AsyncClient(timeout=15.0)
        buffer = bytearray()
        try:
            async with client.stream("POST", url, headers=headers, json=body, params=params) as resp:
                if resp.status_code in (401, 403):
                    raise ProviderAuthError(f"ElevenLabs authentication failure ({resp.status_code})", provider="elevenlabs", status_code=resp.status_code)
                elif resp.status_code == 402:
                    raise ProviderQuotaExhaustedError("ElevenLabs quota/credits exhausted", provider="elevenlabs", status_code=402)
                elif resp.status_code == 429:
                    raise ProviderRateLimitedError("ElevenLabs rate limit exceeded", provider="elevenlabs", status_code=429)
                elif resp.status_code >= 500:
                    raise ProviderUnavailableError(f"ElevenLabs service error HTTP {resp.status_code}", provider="elevenlabs", status_code=resp.status_code)
                elif resp.status_code != 200:
                    raise ProviderError(f"ElevenLabs synthesis failed: HTTP {resp.status_code}", provider="elevenlabs", status_code=resp.status_code)

                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    frames, remainder = self._extract_mp3_frames(bytes(buffer))
                    if frames:
                        buffer = bytearray(remainder)
                        for frame_bytes in frames:
                            await on_audio_chunk(frame_bytes)

                if buffer:
                    await on_audio_chunk(bytes(buffer))
                    buffer.clear()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"ElevenLabs synthesis timed out: {exc}", provider="elevenlabs") from None
        except httpx.NetworkError as exc:
            raise ProviderUnavailableError(f"ElevenLabs network error: {exc}", provider="elevenlabs") from None

    @staticmethod
    def _extract_mp3_frames(data: bytes) -> tuple[list[bytes], bytes]:
        """Extract complete MPEG-1 Layer 3 frames from a byte stream."""
        frames = []
        idx = 0
        bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
        samplerates = [44100, 48000, 32000, 0]
        n = len(data)
        while idx + 4 <= n:
            if data[idx] == 0xFF and (data[idx + 1] & 0xE0) == 0xE0:
                layer = (data[idx + 1] >> 1) & 0x03
                version = (data[idx + 1] >> 3) & 0x03
                br_idx = (data[idx + 2] >> 4) & 0x0F
                sr_idx = (data[idx + 2] >> 2) & 0x03
                padding = (data[idx + 2] >> 1) & 0x01
                if version == 3 and layer == 1 and 0 < br_idx < 15 and sr_idx < 3:
                    br = bitrates[br_idx] * 1000
                    sr = samplerates[sr_idx]
                    flen = int(144 * br / sr) + padding
                    if idx + flen <= n:
                        frames.append(data[idx : idx + flen])
                        idx += flen
                        continue
            idx += 1
        return frames, data[idx:]


class ElevenLabsProvider(VoiceProvider):
    """Voice provider implementation for ElevenLabs (STT + TTS)."""

    def __init__(
        self,
        cfg=None,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        stt_model_id: str | None = None,
        fail_mode: str | None = None,
    ):
        self.cfg = cfg
        self.api_key = api_key if api_key is not None else (getattr(cfg, "elevenlabs_api_key", "") if cfg else "")
        self.voice_id = voice_id if voice_id is not None else (getattr(cfg, "elevenlabs_voice_id", DEFAULT_VOICE_ID) if cfg else DEFAULT_VOICE_ID)
        self.model_id = model_id if model_id is not None else (getattr(cfg, "elevenlabs_model_id", DEFAULT_MODEL_ID) if cfg else DEFAULT_MODEL_ID)
        self.stt_model_id = stt_model_id if stt_model_id is not None else (getattr(cfg, "elevenlabs_stt_model_id", "scribe_v1") if cfg else "scribe_v1")

        if fail_mode is not None:
            self.fail_mode = fail_mode
        else:
            self.fail_mode = getattr(cfg, "elevenlabs_fail_mode", "none") or "none"
        self._stt = ElevenLabsSTT(api_key=self.api_key, model_id=self.stt_model_id)
        self._tts = ElevenLabsTTS(api_key=self.api_key, voice_id=self.voice_id, model_id=self.model_id)
        self._started = False

    @property
    def name(self) -> str:
        return "elevenlabs"

    @property
    def stt(self) -> ElevenLabsSTT:
        return self._stt

    @property
    def tts(self) -> ElevenLabsTTS:
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
        mode = self.fail_mode.lower()
        if mode in ("none", ""):
            return
        if mode in ("quota", "auth", "ratelimit") or mode in ("both", component) or (component in ("stt", "tts") and mode == "all"):
            logger.warning("[ElevenLabsProvider] Triggering simulated failure (mode=%s, component=%s)", mode, component)
            if mode == "quota":
                raise ProviderQuotaExhaustedError("ElevenLabs quota exhausted (simulated 402)", provider="elevenlabs", status_code=402)
            elif mode == "auth":
                raise ProviderAuthError("ElevenLabs API key invalid (simulated 401)", provider="elevenlabs", status_code=401)
            elif mode == "ratelimit":
                raise ProviderRateLimitedError("ElevenLabs rate limit exceeded (simulated 429)", provider="elevenlabs", status_code=429)
            raise ProviderUnavailableError(f"ElevenLabs {component.upper()} unavailable (simulated)", provider="elevenlabs")

    async def check_health(self) -> tuple[bool, str]:
        """Verify ElevenLabs API connectivity safely without exposing secrets.

        Returns:
            (is_healthy: bool, reason: str)
            Reason is one of: healthy, missing_api_key, authentication_failed,
            quota_exhausted, rate_limited, timeout, provider_unavailable.
        """
        if self.fail_mode in ("quota", "auth", "ratelimit", "both", "all", "connect"):
            if self.fail_mode == "auth":
                return False, "authentication_failed"
            elif self.fail_mode == "quota":
                return False, "quota_exhausted"
            elif self.fail_mode == "ratelimit":
                return False, "rate_limited"
            return False, "provider_unavailable"

        if not self.api_key:
            return False, "missing_api_key"

        url = "https://api.elevenlabs.io/v1/user"
        headers = {"xi-api-key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return True, "healthy"
                elif resp.status_code in (401, 403):
                    return False, "authentication_failed"
                elif resp.status_code == 402:
                    return False, "quota_exhausted"
                elif resp.status_code == 429:
                    return False, "rate_limited"
                else:
                    return False, "provider_unavailable"
        except httpx.TimeoutException:
            return False, "timeout"
        except Exception:
            return False, "provider_unavailable"

    async def start(self, tts_language: str = "en-IN") -> None:
        self._check_simulation("connect")
        if not self.api_key:
            raise ProviderAuthError(
                "ELEVENLABS_API_KEY is not configured",
                provider="elevenlabs",
                status_code=401,
            )
        self._check_simulation("stt")
        await self._stt.start()
        self._check_simulation("tts")
        await self._tts.open(tts_language)
        self._started = True
        logger.info("[ElevenLabsProvider] STT and TTS services started.")

    async def stop(self) -> None:
        self._started = False
        try:
            await self._stt.stop()
        except Exception as exc:
            logger.debug("[ElevenLabsProvider] Error stopping STT: %s", exc)
        try:
            await self._tts.close()
        except Exception as exc:
            logger.debug("[ElevenLabsProvider] Error closing TTS: %s", exc)
        logger.info("[ElevenLabsProvider] Stopped.")

    async def send_audio(self, pcm_bytes: bytes) -> None:
        self._check_simulation("stt")
        await self._stt.send_audio(pcm_bytes)

    async def synthesize(
        self, text: str, language_code: str, on_audio_chunk: OnAudioChunk
    ) -> None:
        self._check_simulation("tts")
        await self._tts.synthesize(text, language_code, on_audio_chunk)

    def supports_tts_language(self, language_code: str) -> bool:
        normalized = language_code.lower().split("-")[0]
        return language_code in ELEVENLABS_SUPPORTED_LANGUAGES or normalized in ("en", "hi", "ta", "te", "kn", "ml", "mr", "bn", "gu", "pa", "ur")

    def supports_stt_language(self, language_code: str) -> bool:
        return True

    def map_tts_language(self, language_code: str, fallback: str = "en-IN") -> str:
        if self.supports_tts_language(language_code):
            return language_code
        return fallback
