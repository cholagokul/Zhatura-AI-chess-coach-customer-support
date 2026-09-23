"""Zhatura AI Customer Care — Sarvam streaming TTS + playback (Phase 3).

Persistent WebSocket to Sarvam streaming TTS (bulbul:v3, MP3 chunks).
Each chunk is independently decodable (verified live, 2026-09-21);
chunks are decoded with PyAV and played progressively through the
local speaker via sounddevice — audio starts before the full reply is
synthesized.

Playback supports clean cancellation for barge-in: queued audio is
discarded and the speaker stops immediately. No credentials are logged.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
from collections import deque

import numpy as np

from sarvamai import AsyncSarvamAI  # noqa: F401  (imported lazily-safe)

try:
    from .. import config as _config_module
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as _config_module  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# Language codes TTS supports for spoken replies (Bulbul v3). Sourced
# from the central registry — STT covers more languages than TTS; see
# agent/languages.py and telephony/session.py's capability routing.
try:
    from ..agent.languages import TTS_SUPPORTED_CODES
except ImportError:  # pragma: no cover
    from agent.languages import TTS_SUPPORTED_CODES  # type: ignore

TTS_LANGUAGES = set(TTS_SUPPORTED_CODES)


class StreamingTTSError(Exception):
    """Streaming TTS connection/config/playback failure."""


def select_tts_language(stt_language: "str | None") -> str:
    """Map a detected STT language to a supported TTS language.

    Returns a safe spoken language — callers that must KNOW when the
    language has no Bulbul voice use ``agent.languages.supports_tts``
    instead (telephony session routes explicitly and logs
    TTS_UNAVAILABLE_FOR_LANGUAGE)."""
    if stt_language in TTS_LANGUAGES:
        return stt_language
    return "en-IN"


class StreamingTTS:
    """Streaming text-to-speech over one persistent WebSocket."""

    def __init__(self, cfg=None, client=None):
        if cfg is None:
            cfg = _config_module.load_config()
        self.cfg = cfg
        if client is None:
            from sarvamai import AsyncSarvamAI

            client = AsyncSarvamAI(api_subscription_key=cfg.sarvam_api_key)
        self._client = client
        self._ctx = None
        self._ws = None
        self.is_open = False

    async def open(self, language_code: str = "en-IN") -> None:
        if self.is_open:
            return
        self._ctx = self._client.text_to_speech_streaming.connect(
            model="bulbul:v3", send_completion_event="true"
        )
        try:
            self._ws = await self._ctx.__aenter__()
            await self.configure(language_code)
        except Exception as exc:
            raise StreamingTTSError(_safe_ws_error(exc)) from None
        self.is_open = True
        logger.info("Streaming TTS connected (bulbul:v3, speaker=%s).",
                    self.cfg.tts_speaker)

    async def configure(self, language_code: str) -> None:
        await self._ws.configure(
            target_language_code=language_code,
            speaker=self.cfg.tts_speaker,
            speech_sample_rate=self.cfg.tts_stream_sample_rate,
            enable_preprocessing=True,
            output_audio_codec="mp3",
        )
        self.current_language = language_code

    async def close(self) -> None:
        self.is_open = False
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._ctx = None
        self._ws = None
        logger.info("Streaming TTS connection closed.")

    async def synthesize(self, text: str, language_code: str,
                         on_audio_chunk) -> None:
        """Send ``text``; invoke ``on_audio_chunk(mp3_bytes)`` per chunk.

        The callback fires as chunks arrive (progressive). Returns when
        the server signals the final event for this utterance.
        """
        if getattr(self, "current_language", None) != language_code:
            await self.configure(language_code)
        try:
            await self._ws.convert(text)
            await self._ws.flush()
            while True:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30)
                name = type(msg).__name__
                if name == "AudioOutput":
                    await on_audio_chunk(base64.b64decode(msg.data.audio))
                elif name == "EventResponse" and msg.data.event_type == "final":
                    return
                elif name == "ErrorResponse":
                    raise StreamingTTSError(
                        f"TTS server error: {getattr(msg.data, 'message', 'unknown')}"
                    )
        except (asyncio.TimeoutError, StreamingTTSError):
            raise
        except Exception as exc:
            self.is_open = False
            raise StreamingTTSError(_safe_ws_error(exc)) from None


def decode_mp3_to_pcm16(mp3_bytes: bytes, sample_rate: int):
    """Decode one self-contained MP3 chunk to mono int16 ``numpy`` PCM
    at ``sample_rate``. Returns None when undecodable. Shared by the
    local SpeakerPlayer and the Phase 4 telephony audio sink."""
    import av

    try:
        container = av.open(io.BytesIO(mp3_bytes), format="mp3")
        frames = []
        for frame in container.decode(audio=0):
            resampler = av.audio.resampler.AudioResampler(
                format="s16", layout="mono", rate=sample_rate
            )
            for rframe in resampler.resample(frame):
                frames.append(rframe.to_ndarray().reshape(-1))
        container.close()
    except Exception as exc:
        logger.warning("Skipping undecodable audio chunk (%s).",
                       type(exc).__name__)
        return None
    if not frames:
        return None
    return np.concatenate(frames)


class SpeakerPlayer:
    """Progressive PCM playback with instant cancellation (barge-in).

    Decoded int16 frames are queued; a sounddevice output callback
    drains the queue. ``cancel()`` discards everything queued and
    playing immediately.
    """

    def __init__(self, sample_rate: int = 22050):
        self.sample_rate = sample_rate
        self._queue: deque[np.ndarray] = deque()
        self._cancelled = threading.Event()
        self._drained = threading.Event()
        self._drained.set()  # nothing queued yet → already drained
        self._stream = None
        self._lock = threading.Lock()
        self.playing = False

    def _open_stream(self) -> None:
        import sounddevice as sd

        if self._stream is None:
            self.playing = True
            self._drained.clear()

            def callback(outdata, frames, _time, status):  # noqa: ANN001
                filled = 0
                with self._lock:
                    while filled < frames and self._queue:
                        chunk = self._queue[0]
                        take = min(frames - filled, len(chunk))
                        outdata[filled:filled + take, 0] = chunk[:take]
                        filled += take
                        if take == len(chunk):
                            self._queue.popleft()
                        else:
                            self._queue[0] = chunk[take:]
                if filled < frames:
                    outdata[filled:, 0] = 0
                    if not self._queue:
                        self._drained.set()

            self._stream = sd.OutputStream(
                samplerate=self.sample_rate, channels=1,
                dtype="int16", callback=callback,
            )
            self._stream.start()
            logger.info("Speaker playback started (%d Hz).", self.sample_rate)

    def feed_pcm(self, pcm: np.ndarray) -> None:
        """Queue mono int16 samples for playback."""
        if self._cancelled.is_set():
            return
        self._open_stream()
        self._drained.clear()
        self.playing = True
        with self._lock:
            self._queue.append(pcm.astype(np.int16))

    def feed_mp3_chunk(self, mp3_bytes: bytes) -> None:
        """Decode one self-contained MP3 chunk and queue it."""
        if self._cancelled.is_set():
            return
        frames = decode_mp3_to_pcm16(mp3_bytes, self.sample_rate)
        if frames is not None:
            self.feed_pcm(frames)

    def cancel(self) -> None:
        """Barge-in: discard everything queued; speaker goes silent."""
        self._cancelled.set()
        with self._lock:
            self._queue.clear()
        self._drained.set()
        self.playing = False
        logger.info("Playback cancelled (barge-in).")

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self.playing = False

    def finish(self) -> None:
        """Signal end-of-utterance: play out the remainder (no close)."""
        deadline = 30.0
        waited = 0.0
        while not self._cancelled.is_set() and not self._drained.wait(0.05):
            waited += 0.05
            if waited >= deadline:
                logger.warning("Playback drain timed out; stopping.")
                break
        self.playing = False

    def close(self) -> None:
        """Final shutdown — stop the stream. Call once at session end."""
        self.cancel()
        self._close_stream()

    def reset_for_next(self) -> None:
        """Prepare for the next utterance; reuses the open stream."""
        self._cancelled.clear()
        self._drained.clear()


def _safe_ws_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "authentication failure (check API key)"
    if status == 402:
        return "quota/credits exhausted (top up the Sarvam account)"
    return type(exc).__name__
