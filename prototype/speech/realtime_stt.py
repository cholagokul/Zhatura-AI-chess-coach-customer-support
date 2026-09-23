"""Zhatura AI Customer Care — Sarvam realtime streaming STT (Phase 3).

Wraps the official async SDK WebSocket
(``speech_to_text_realtime_streaming.connect``) with saaras:v4, VAD
endpointing, linear16/16kHz audio, and the mandatory Zhatura
terminology prompt (Phase 2/3 finding).

Application code receives plain events; it never touches WebSocket
details. Never logs or exposes credentials or audio payloads.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Callable

from sarvamai import AsyncSarvamAI
from sarvamai.types import RealtimeAudioInput, RealtimeFlush

try:
    from .. import config as _config_module
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as _config_module  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Callback types
OnSpeechStart = Callable[[], None]
OnSpeechEnd = Callable[[], None]
OnPartial = Callable[[str], None]
OnFinal = Callable[[str, str], None]          # (text, language_code)
OnEvent = Callable[[str], None]

MAX_RECONNECTS = 3
CHUNK_MS = 100
CHUNK_BYTES = 3200  # 100 ms of 16 kHz 16-bit mono PCM


class RealtimeSTTError(Exception):
    """Fatal realtime STT condition (recovery not possible/safe)."""


class RealtimeSTT:
    """One realtime STT session over a Sarvam WebSocket."""

    def __init__(
        self,
        cfg=None,
        client: "AsyncSarvamAI | None" = None,
        *,
        on_speech_start: "OnSpeechStart | None" = None,
        on_speech_end: "OnSpeechEnd | None" = None,
        on_partial: "OnPartial | None" = None,
        on_final: "OnFinal | None" = None,
        on_error: "OnEvent | None" = None,
    ):
        if cfg is None:
            cfg = _config_module.load_config()
        self.cfg = cfg
        self._client = client or AsyncSarvamAI(
            api_subscription_key=cfg.sarvam_api_key
        )
        self.on_speech_start = on_speech_start or (lambda: None)
        self.on_speech_end = on_speech_end or (lambda: None)
        self.on_partial = on_partial or (lambda _: None)
        self.on_final = on_final or (lambda _t, _l: None)
        self.on_error = on_error or (lambda _m: None)

        self._ws = None
        self._ctx = None
        self._receiver_task: "asyncio.Task | None" = None
        self._running = False

    # -- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        """Open the WebSocket and begin receiving events."""
        if self._running:
            return
        self._ctx = self._client.speech_to_text_realtime_streaming.connect(
            language_code=self.cfg.realtime_stt_language,
            model=self.cfg.realtime_stt_model,
            stream_type=self.cfg.realtime_stt_stream_type,
            mode=self.cfg.stt_mode,
            prompt=self.cfg.stt_prompt,
            endpointing="vad",
            encoding="linear16",
            sample_rate=str(self.cfg.microphone_sample_rate),
            threshold=str(self.cfg.stt_vad_threshold),
            silence_duration_ms=str(self.cfg.stt_silence_duration_ms),
            min_speech_duration_ms=str(self.cfg.stt_min_speech_duration_ms),
        )
        try:
            self._ws = await self._ctx.__aenter__()
        except Exception as exc:
            raise RealtimeSTTError(_safe_ws_error(exc)) from None
        self._running = True
        self._receiver_task = asyncio.create_task(
            self._receive_loop(), name="realtime-stt-rx"
        )
        logger.info(
            "Realtime STT connected (model=%s, stream_type=%s, lang=%s).",
            self.cfg.realtime_stt_model,
            self.cfg.realtime_stt_stream_type,
            self.cfg.realtime_stt_language,
        )

    async def stop(self) -> None:
        """Close the WebSocket and stop receiving. Idempotent."""
        self._running = False
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receiver_task = None
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._ctx = None
            self._ws = None
        logger.info("Realtime STT connection closed.")

    # -- sending ------------------------------------------------------

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send one 16 kHz linear16 PCM chunk."""
        if not self._running or self._ws is None:
            return
        try:
            await self._ws.send_realtime_audio_input(
                RealtimeAudioInput(audio=base64.b64encode(pcm_bytes).decode())
            )
        except Exception as exc:
            logger.warning("Realtime STT send failed: %s", _safe_ws_error(exc))
            await self._handle_disconnect()

    async def flush(self) -> None:
        """Ask the server to finalize any open utterance."""
        if self._running and self._ws is not None:
            try:
                await self._ws.send_realtime_flush(RealtimeFlush())
            except Exception:
                pass

    # -- receiving ----------------------------------------------------

    async def _receive_loop(self) -> None:
        while self._running:
            try:
                msg = await self._ws.recv()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if self._running:
                    logger.warning("Realtime STT connection dropped: %s",
                                   _safe_ws_error(exc))
                    await self._handle_disconnect()
                return

            name = type(msg).__name__
            if name == "RealtimeTranscriptPartial":
                if msg.text:
                    self.on_partial(msg.text)
            elif name == "RealtimeTranscriptFinal":
                if msg.text:
                    self.on_final(msg.text, msg.language or self.cfg.stt_language)
            elif name == "RealtimeVadSpeechStart":
                self.on_speech_start()
            elif name == "RealtimeVadSpeechEnd":
                self.on_speech_end()
            elif name == "RealtimeError":
                logger.error("Realtime STT error (fatal=%s): %s",
                             getattr(msg, "is_fatal", "?"),
                             getattr(msg, "message", "unknown"))
                self.on_error(getattr(msg, "message", "unknown"))
                if getattr(msg, "is_fatal", False):
                    await self._handle_disconnect()
                    return

    async def _handle_disconnect(self) -> None:
        """Attempt limited reconnection with short backoff."""
        await self._teardown_transport()
        for attempt in range(1, MAX_RECONNECTS + 1):
            logger.info("Realtime STT reconnect attempt %d/%d...",
                        attempt, MAX_RECONNECTS)
            await asyncio.sleep(min(0.5 * 2 ** (attempt - 1), 4.0))
            try:
                self._ctx = (
                    self._client.speech_to_text_realtime_streaming.connect(
                        language_code=self.cfg.realtime_stt_language,
                        model=self.cfg.realtime_stt_model,
                        stream_type=self.cfg.realtime_stt_stream_type,
                        mode=self.cfg.stt_mode,
                        prompt=self.cfg.stt_prompt,
                        endpointing="vad",
                        encoding="linear16",
                        sample_rate=str(self.cfg.microphone_sample_rate),
                        threshold=str(self.cfg.stt_vad_threshold),
                        silence_duration_ms=str(self.cfg.stt_silence_duration_ms),
                        min_speech_duration_ms=str(self.cfg.stt_min_speech_duration_ms),
                    )
                )
                self._ws = await self._ctx.__aenter__()
                self._running = True
                self._receiver_task = asyncio.create_task(
                    self._receive_loop(), name="realtime-stt-rx"
                )
                logger.info("Realtime STT reconnected.")
                return
            except Exception as exc:
                logger.warning("Reconnect failed: %s", _safe_ws_error(exc))
        self.on_error("Realtime STT connection lost permanently.")

    async def _teardown_transport(self) -> None:
        self._running = False
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._ctx = None
        self._ws = None


def _safe_ws_error(exc: Exception) -> str:
    """Redact-safe WebSocket/HTTP error text (no credentials)."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "authentication failure (check API key)"
    if status == 402:
        return "quota/credits exhausted (top up the Sarvam account)"
    name = type(exc).__name__
    return f"{name}"
