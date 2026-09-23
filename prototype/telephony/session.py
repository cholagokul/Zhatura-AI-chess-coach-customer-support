"""Zhatura AI Customer Care — per-call telephony session (Phase 4).

One CallSession = one telephone call. It wires the Exotel transport to
the transport-agnostic Phase 3 pipeline:

    Exotel media → decode/resample → Sarvam realtime STT →
    brand correction → VoiceAgent (sarvam-105b-conversations) →
    Sarvam streaming TTS → PCM → Exotel media → caller's phone

Isolation rule: every call constructs its own Conversation, state
machine, STT socket, TTS socket, queues and counters. Nothing leaks
between calls.

No secrets, caller phone numbers, or raw audio are persisted. Call
metadata + transcripts go to prototype/logs/calls/ (git-ignored).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from pathlib import Path

from agent.conversation import Conversation
from agent.languages import (
    language_name,
    match_language_alias,
    normalize_language_code,
    supports_tts,
)
from agent.state import AgentState, AgentStateMachine
from agent.voice_agent import (
    CLOSING_TEXT,
    SILENCE_PROMPT_TEXT,
    TurnTimings,
    VoiceAgent,
    detect_language_switch,
)
from speech.realtime_stt import RealtimeSTT
from speech.streaming_tts import StreamingTTS, decode_mp3_to_pcm16
from speech.providers import (
    VoiceProvider,
    VoiceProviderManager,
    AllProvidersUnavailableError,
    FailoverLimitExceededError,
    ProviderError,
    get_emergency_audio_pcm,
)
from telephony import exotel_events

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CALL_LOG_DIR = PROJECT_ROOT / "prototype" / "logs" / "calls"

GREETING_TEXT = ("Hello, welcome to Zhatura customer support. "
                 "How can I help you today?")

# Lightweight human-transfer intent detection (actual transfer is a
# later phase; we only acknowledge + record the request).
_HUMAN_HINTS = ("human", "real person", "representative", "support agent",
                "customer care agent", "agent please")

# Upper bound for waiting on the Exotel mark echo (= caller heard the
# whole utterance). Generous: 45 s of buffered speech is a long reply.
_MARK_TIMEOUT_S = 45.0

# Sarvam realtime STT 'fast' stream rejects frames above 16000 bytes.
MAX_STT_FRAME_BYTES = 16000


class TelephonyAudioSink:
    """SpeakerPlayer-compatible sink that streams PCM to Exotel instead
    of the Mac speaker — **paced in real time**.

    Outbound audio design (fixes choppy PSTN audio): Sarvam streams MP3
    chunks much faster than real time. Sending them to Exotel as they
    arrive floods the telephone playout buffer with irregular bursts,
    which the caller hears as broken/choppy audio. Instead:

        decoded PCM (tts_rate) → shared byte buffer
            → loop-thread pacer task → ONE fixed-size frame per
              frame period (real-time cadence) → Exotel media event

    VoiceAgent calls feed/finish through ``run_in_executor`` (worker
    threads); the pacer lives on the asyncio loop. Playback completion
    is known via Exotel ``mark`` echo events; barge-in clears the
    buffer and interrupts Exotel's playout with a ``clear`` event.
    """

    # Outbound telephony frame: 100 ms of audio per Exotel media event.
    FRAME_MS = 100
    # Small jitter buffer bound: never hold more than this much unsent
    # audio (barge-in always flushes it anyway).
    MAX_BUFFER_S = 15.0

    def __init__(self, transport, loop: asyncio.AbstractEventLoop,
                 tts_rate: int, frame_ms: "int | None" = None):
        self._transport = transport
        self._loop = loop
        self._tts_rate = tts_rate
        self.frame_ms = frame_ms or self.FRAME_MS
        self._frame_bytes = tts_rate * 2 * self.frame_ms // 1000
        self._max_buffer_bytes = tts_rate * 2 * int(self.MAX_BUFFER_S)
        self._cancelled = threading.Event()
        self._buffer = bytearray()
        self._futs: "list" = []
        self._lock = threading.Lock()
        self._utterance_seq = 0
        self._pending_marks: "dict[str, threading.Event]" = {}
        self._pacer_task: "asyncio.Task | None" = None
        self._final_requested = threading.Event()
        self.first_send_at: "float | None" = None
        # Per-utterance audio debug metrics (§19).
        self._chunks_sent = 0
        self._bytes_sent = 0
        self._max_buffer_seen = 0
        self._pace_started_at: "float | None" = None

    # -- lifecycle (event loop) -----------------------------------------

    def start_pacer(self) -> None:
        """Start the paced sender task. Call from the event loop."""
        if self._pacer_task is None or self._pacer_task.done():
            self._pacer_task = self._loop.create_task(self._pace())

    async def stop(self) -> None:
        """Stop the pacer task (session shutdown)."""
        task = self._pacer_task
        self._pacer_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _pace(self) -> None:
        """Send one fixed-size frame every frame_ms — real-time pacing."""
        period = self.frame_ms / 1000.0
        while True:
            if self._cancelled.is_set():
                await asyncio.sleep(0.01)
                continue
            with self._lock:
                if len(self._buffer) >= self._frame_bytes:
                    frame = bytes(self._buffer[:self._frame_bytes])
                    del self._buffer[:self._frame_bytes]
                elif self._final_requested.is_set() and self._buffer:
                    # Utterance tail (< one frame): flush it so
                    # finish() never parks on a few ms of audio. Full
                    # frames above still go out at real-time cadence.
                    frame = bytes(self._buffer)
                    del self._buffer[:]
                else:
                    frame = None
            if frame is None:
                await asyncio.sleep(0.005)
                continue
            try:
                await self._transport.send_audio(frame, self._tts_rate)
            except Exception:
                await asyncio.sleep(period)
                continue
            now = time.monotonic()
            if self.first_send_at is None:
                self.first_send_at = now
            if self._pace_started_at is None:
                self._pace_started_at = now
            self._chunks_sent += 1
            self._bytes_sent += len(frame)
            logger.debug("TTS OUT frame: bytes=%d duration=%dms",
                         len(frame), self.frame_ms)
            await asyncio.sleep(period)

    def _buffer_depth(self) -> int:
        with self._lock:
            return len(self._buffer)

    # -- VoiceAgent/player interface -------------------------------------

    def reset_for_next(self) -> None:
        self._cancelled.clear()
        self._final_requested.clear()
        # Fresh timestamps per utterance so telephony latency metrics
        # measure each turn, not the greeting or a previous reply.
        self.first_send_at = None
        self._chunks_sent = 0
        self._bytes_sent = 0
        self._max_buffer_seen = 0
        self._pace_started_at = None

    def feed_mp3_chunk(self, mp3_bytes: bytes) -> None:
        if self._cancelled.is_set():
            return
        # Decode off the event loop (this runs in a worker thread).
        pcm = decode_mp3_to_pcm16(mp3_bytes, self._tts_rate)
        if pcm is None:
            return
        # Lazy pacer start: feeding audio must work even if start_pacer
        # wasn't called yet (defense against caller ordering bugs).
        try:
            self._loop.call_soon_threadsafe(self.start_pacer)
        except Exception:
            pass
        data = pcm.tobytes()
        with self._lock:
            if len(self._buffer) + len(data) > self._max_buffer_bytes:
                logger.warning("Telephony output buffer full; dropping "
                               "audio chunk.")
                return
            self._buffer += data
            self._max_buffer_seen = max(self._max_buffer_seen,
                                        len(self._buffer))

    def feed_pcm_chunk(self, pcm_bytes: bytes) -> None:
        """Feed raw mono 16-bit linear PCM directly (bypassing MP3 decode)."""
        if self._cancelled.is_set():
            return
        try:
            self._loop.call_soon_threadsafe(self.start_pacer)
        except Exception:
            pass
        with self._lock:
            if len(self._buffer) + len(pcm_bytes) > self._max_buffer_bytes:
                logger.warning("Telephony output buffer full; dropping audio chunk.")
                return
            self._buffer += pcm_bytes
            self._max_buffer_seen = max(self._max_buffer_seen, len(self._buffer))

    def _wait_buffer_drained(self) -> None:
        """Worker thread: block until the pacer has sent the buffer."""
        start = time.monotonic()
        deadline = self.MAX_BUFFER_S + 10.0
        while not self._cancelled.is_set():
            with self._lock:
                if not self._buffer:
                    return
            if time.monotonic() - start > deadline:
                logger.warning("Telephony buffer drain timed out.")
                return
            time.sleep(0.05)

    def finish(self) -> None:
        """Wait until the caller has heard the whole utterance.

        Waits for the pacer to flush the buffer (including the partial
        tail frame), then sends a mark and waits (bounded) for the
        Exotel mark echo. Barge-in cancels the wait instantly.
        """
        if self._cancelled.is_set():
            return
        self._final_requested.set()
        self._wait_buffer_drained()
        if self._pace_started_at is not None:
            logger.info(
                "TTS OUT: rate=%d frame=%dB/%dms chunks=%d "
                "bytes=%d max_buffer=%dB",
                self._tts_rate, self._frame_bytes, self.frame_ms,
                self._chunks_sent, self._bytes_sent, self._max_buffer_seen)
        if self._cancelled.is_set():
            return
        self._utterance_seq += 1
        name = f"utterance-{self._utterance_seq}"
        done = threading.Event()
        self._pending_marks[name] = done
        try:
            asyncio.run_coroutine_threadsafe(
                self._transport.send_mark(name), self._loop
            ).result(timeout=5)
        except Exception:
            self._pending_marks.pop(name, None)
            return
        done.wait(timeout=_MARK_TIMEOUT_S)
        # Timed-out waits fall through; the state machine recovers on
        # the next caller event.
        self._pending_marks.pop(name, None)

    def cancel(self) -> None:
        """Barge-in: drop unsent audio and clear Exotel's buffer.

        Called from STT callbacks running on the event-loop thread, so
        the clear must be scheduled WITHOUT blocking the loop.
        """
        self._cancelled.set()
        self._final_requested.clear()
        with self._lock:
            self._buffer.clear()
            self._futs.clear()
        for event in self._pending_marks.values():
            event.set()
        try:
            asyncio.run_coroutine_threadsafe(
                self._transport.clear_audio(), self._loop)
        except Exception:
            pass
        logger.info("Telephony playback cancelled (barge-in).")

    def close(self) -> None:
        self.cancel()

    # -- mark echo from the receive loop ---------------------------------

    def notify_mark(self, name: str) -> None:
        event = self._pending_marks.pop(name, None)
        if event is not None:
            event.set()


class CallSession:
    """Orchestrates one telephone call end to end."""

    def __init__(self, cfg, transport, sarvam_client=None,
                 registry: "dict | None" = None,
                 provider_manager: "VoiceProviderManager | None" = None):
        self.cfg = cfg
        self.transport = transport
        # Optional shared registry (stream_sid → CallSession) for
        # duplicate-session defense: Exotel reconnecting with the same
        # stream triggers a clean shutdown of the stale session.
        self._registry = registry
        self._finalized = False
        self.state = AgentStateMachine()

        # Phase 7.1 dual voice provider management & call locking
        self._provider_manager = provider_manager or VoiceProviderManager(
            cfg=cfg, sarvam_client=sarvam_client
        )
        self.provider_generation = 0
        self.failover_count = 0
        self.failover_occurred = False
        self.failover_reason = ""
        self._failover_lock = asyncio.Lock()

        # Select initial voice provider (locked for the call unless failover occurs)
        try:
            self._provider, self.active_voice_provider = (
                self._provider_manager.select_initial_provider(
                    stt_cls=RealtimeSTT, tts_cls=StreamingTTS
                )
            )
        except AllProvidersUnavailableError as exc:
            logger.critical("[%s] No voice providers available at call start: %s", "call", exc)
            self._provider = self._provider_manager.create_provider(
                "sarvam", stt_cls=RealtimeSTT, tts_cls=StreamingTTS
            )
            self.active_voice_provider = "sarvam"
            self.disconnect_reason = "dual_provider_failure"

        self.initial_voice_provider = self.active_voice_provider
        self.stt = self._provider.stt
        self.tts = self._provider.tts

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

        self.sink = TelephonyAudioSink(
            transport, loop, cfg.tts_stream_sample_rate)
        chat_client = getattr(self.stt, "_client", sarvam_client)
        self.agent = VoiceAgent(
            cfg=cfg,
            conversation=Conversation.from_prompt_file(
                max_turns=cfg.max_conversation_turns),
            chat_client=chat_client,
            tts=self.tts,
            player=self.sink,
        )

        # Call metadata (§28) — no secrets, no caller numbers.
        self.session_id = f"call-{uuid.uuid4().hex[:8]}"
        self.call_id = ""
        self.stream_id = ""
        self.connected_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.started_at = ""
        self.ended_at = ""
        # Per-call language state (Phase 4.1). Nothing here survives a
        # call — each CallSession is a fresh instance per WebSocket.
        self.detected_language = ""     # latest saaras:v4 auto-detection
        self.requested_language = ""    # last explicit caller switch
        self.reply_language = "en-IN"   # LLM reply target this call
        # spoken voice language (reply_language, or the configured
        # fallback when Bulbul has no voice for it)
        self.tts_language = cfg.tts_language
        self._tts_unavailable_logged: "set[str]" = set()
        self._fallback_choice_pending = False
        self.turn_count = 0
        self.barge_in_count = 0
        self.human_requested = False
        self.disconnect_reason = ""
        self.turns: "list[dict]" = []
        self.latencies: "list[dict]" = []

        self._turn_queue: asyncio.Queue = asyncio.Queue()
        self._turn_worker: "asyncio.Task | None" = None
        self._silence_task: "asyncio.Task | None" = None
        self._greet_task: "asyncio.Task | None" = None
        self._run_task: "asyncio.Task | None" = None
        self._last_speech_end: "float | None" = None
        self._last_activity = time.monotonic()
        self._reminded = False
        self._stop = asyncio.Event()
        self._media_active_logged = False

        # STT event wiring with generation checks
        self._wire_provider_stt(self._provider, self.provider_generation)
        logger.info("[%s] CALL CREATED (provider=%s).", self.session_id, self.active_voice_provider)

    def _wire_provider_stt(self, provider: VoiceProvider, generation: int) -> None:
        """Wire STT callbacks for the active provider with generation checks."""
        def on_speech_start():
            if self.provider_generation != generation:
                return
            self._on_speech_start()

        def on_speech_end():
            if self.provider_generation != generation:
                return
            self._on_speech_end()

        def on_final(text: str, lang: str):
            if self.provider_generation != generation:
                logger.info(
                    "[%s] Ignored stale STT transcript from gen %d (current=%d): %s",
                    self.session_id, generation, self.provider_generation, text
                )
                return
            self._on_final(text, lang)

        def on_error(err_msg: str):
            if self.provider_generation != generation:
                return
            logger.error("[%s] STT error (%s, gen %d): %s",
                         self.session_id, self.active_voice_provider, generation, err_msg)
            lowered = err_msg.lower()
            if any(k in lowered for k in ("quota", "auth", "rate", "fail", "unavailable", "timeout")):
                asyncio.create_task(self.failover_provider(f"stt_error: {err_msg}"))

        provider.wire_stt_callbacks(
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end,
            on_final=on_final,
            on_error=on_error,
        )
        # Also assign to self.stt for backward compatibility with tests
        self.stt.on_speech_start = on_speech_start
        self.stt.on_speech_end = on_speech_end
        self.stt.on_final = on_final
        self.stt.on_error = on_error

    async def failover_provider(self, reason: str) -> bool:
        """Perform a single controlled failover to the secondary voice provider."""
        async with self._failover_lock:
            max_failovers = getattr(self.cfg, "max_provider_failovers_per_call", 1)
            if self.failover_count >= max_failovers:
                logger.error(
                    "[%s] Failover denied: maximum allowed failovers (%d) reached for this call.",
                    self.session_id, self.failover_count
                )
                await self._play_emergency_and_hangup(reason)
                return False

            old_name = self.active_voice_provider
            try:
                new_provider, new_name = self._provider_manager.get_failover_candidate(
                    old_name, self.failover_count, stt_cls=RealtimeSTT, tts_cls=StreamingTTS
                )
            except Exception as exc:
                logger.error("[%s] Failover candidate selection failed: %s", self.session_id, exc)
                await self._play_emergency_and_hangup(reason)
                return False

            # Invalidate in-flight audio/transcript events
            self.provider_generation += 1
            gen = self.provider_generation

            # Cancel current audio output (sends clear to Exotel)
            self.sink.cancel()

            # Record failure of old provider
            self._provider_manager.record_failure(old_name, reason)

            # Close old provider
            old_provider = self._provider
            try:
                await old_provider.stop()
            except Exception as exc:
                logger.warning("[%s] Error stopping old provider %s: %s", self.session_id, old_name, exc)

            # Switch active provider
            self._provider = new_provider
            self.active_voice_provider = new_name
            self.failover_occurred = True
            self.failover_reason = reason
            self.failover_count += 1
            self.stt = new_provider.stt
            self.tts = new_provider.tts
            self.agent.tts = new_provider.tts

            try:
                tts_lang, _ = self._route_tts_language(self.reply_language)
                await new_provider.start(tts_lang)
                self._wire_provider_stt(new_provider, gen)
                logger.warning(
                    "[%s] FAILOVER COMPLETE: %s -> %s (reason: %s, generation: %d, language: %s).",
                    self.session_id, old_name, new_name, reason, gen, self.reply_language
                )
                return True
            except Exception as exc:
                logger.critical("[%s] Failed to start new provider %s: %s", self.session_id, new_name, exc)
                self._provider_manager.record_failure(new_name, f"failover_start_failure: {exc}")
                await self._play_emergency_and_hangup(f"failover_start_failed: {exc}")
                return False

    async def _play_emergency_and_hangup(self, reason: str) -> None:
        """Play static 16kHz emergency audio directly to Exotel and terminate call cleanly."""
        logger.critical(
            "[%s] DUAL PROVIDER OUTAGE: Playing emergency audio and ending call (reason: %s).",
            self.session_id, reason
        )
        self.disconnect_reason = "dual_provider_failure"
        self.sink.cancel()
        try:
            emergency_pcm = get_emergency_audio_pcm()
            await self.transport.send_audio(emergency_pcm, 16000)
            await asyncio.sleep(2.0)
        except Exception as exc:
            logger.warning("[%s] Failed sending emergency audio: %s", self.session_id, exc)
        finally:
            await self.transport.close()
            await self._stop_soon()

    # Back-compat: the stabilization phase referred to a single
    # ``session.language`` — it now means the caller-requested language
    # (reply target), which is exactly how the Phase 4 tests used it.
    @property
    def language(self) -> str:
        return self.reply_language

    @language.setter
    def language(self, code: str) -> None:
        self.requested_language = code
        self.reply_language = code

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Drive the call until stop/disconnect. Always finalizes."""
        await self.transport.start()
        self.sink.start_pacer()
        try:
            await self._provider.start(self.cfg.tts_language)
            logger.info("[%s] VOICE PROVIDER STARTED (%s).", self.session_id, self.active_voice_provider)
        except Exception as exc:
            logger.error("[%s] Initial provider %s start failed: %s",
                         self.session_id, self.active_voice_provider, exc)
            failover_ok = await self.failover_provider(f"provider_start_failure: {exc}")
            if not failover_ok:
                await self.shutdown()
                return

        self._silence_task = asyncio.create_task(self._silence_watchdog())
        self._turn_worker = asyncio.create_task(self._turn_loop())
        self._run_task = asyncio.current_task()
        logger.info("[%s] Call session started.", self.session_id)
        try:
            while True:
                event = await self.transport.receive()
                await self._handle_event(event)
                if self._stop.is_set():
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # TransportClosed or anything else: finalize, no traces.
            self.disconnect_reason = self.disconnect_reason or "ws_disconnect"
            logger.info("[%s] Call disconnected (%s).",
                        self.session_id, type(exc).__name__)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Idempotent cleanup: safe to call any number of times.

        Every disconnect path (caller hangup, Exotel stop, our own
        end-call close, network loss, ngrok drop) converges here.
        """
        if self._finalized:
            return
        self._finalized = True
        logger.info("[%s] SESSION CLEANUP START.", self.session_id)
        self._stop.set()
        try:
            self.state.transition(AgentState.STOPPING)
        except Exception:
            pass
        if not self.disconnect_reason:
            self.disconnect_reason = "session_end"
        self.ended_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        for task in (self._silence_task, self._turn_worker,
                     self._greet_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        try:
            self.sink.close()
        except Exception:
            pass
        await self.sink.stop()
        if hasattr(self, "_provider") and self._provider is not None:
            try:
                await self._provider.stop()
            except Exception:
                pass
        else:
            await self.stt.stop()
            await self.tts.close()
        if hasattr(self.agent, "tool_service") and self.agent.tool_service is not None:
            try:
                self.agent.tool_service.reset()
            except Exception:
                pass
        if not self.transport.connected:
            pass  # already closed (e.g. our end-call close)
        else:
            logger.info("[%s] WSS CLOSING.", self.session_id)
        await self.transport.close()
        if (self._registry is not None
                and self._registry.get(self.stream_id) is self):
            self._registry.pop(self.stream_id, None)
        # If shutdown() was triggered from OUTSIDE run() (duplicate
        # stream defense, operator action), run()'s receive loop can
        # remain parked if the peer never answers our close — cancel it
        # so the handler always returns and active_calls drains.
        task = self._run_task
        if (task is not None and task is not asyncio.current_task()
                and not task.done()):
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        path = self._save_call_log()
        logger.info("[%s] SESSION CLEANUP COMPLETE. reason=%s turns=%d "
                    "barge_ins=%d → %s",
                    self.session_id, self.disconnect_reason,
                    self.turn_count, self.barge_in_count, path)

    # ------------------------------------------------------------------
    # Exotel event handling
    # ------------------------------------------------------------------

    async def _handle_event(self, event) -> None:
        if isinstance(event, exotel_events.ConnectedEvent):
            logger.info("[%s] Exotel WebSocket connected.", self.session_id)
            return

        if isinstance(event, exotel_events.StartEvent):
            self.call_id = event.call_sid
            self.stream_id = event.stream_sid
            self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            # Duplicate-stream defense: if Exotel reconnects the same
            # stream while an old session is (incorrectly) still alive,
            # cleanly shut the stale session down before continuing —
            # no duplicate background pipelines.
            if self._registry is not None and self.stream_id:
                stale = self._registry.get(self.stream_id)
                if stale is not None and stale is not self:
                    logger.warning(
                        "[%s] Duplicate stream_sid %s — shutting down "
                        "stale session %s.",
                        self.session_id, self.stream_id,
                        stale.session_id)
                    try:
                        await stale.shutdown()
                    except Exception:
                        pass
                self._registry[self.stream_id] = self
            logger.info(
                "[%s] EXOTEL START (call_id=%s, stream_id=%s, "
                "custom_params=%s).",
                self.session_id, self.call_id or "?", self.stream_id,
                list(event.custom_param_keys) or "none")
            if self.cfg.auto_greeting:
                self._greet_task = asyncio.create_task(self._greet())
            return

        if isinstance(event, exotel_events.MediaEvent):
            self.transport.media_received += 1
            if not self._media_active_logged:
                self._media_active_logged = True
                logger.info("[%s] MEDIA ACTIVE (rate=%d Hz).",
                            self.session_id,
                            self.transport.serializer.exotel_sample_rate)
            pcm16k = self.transport.serializer.decode_media_to_internal(
                event.payload, self.cfg.microphone_sample_rate)
            try:
                await self._provider.send_audio(pcm16k)
            except Exception as exc:
                logger.error("[%s] Provider send_audio failed (%s): %s",
                             self.session_id, self.active_voice_provider, exc)
                await self.failover_provider(f"stt_send_audio_error: {exc}")
            return

        if isinstance(event, exotel_events.MarkEvent):
            self.sink.notify_mark(event.name)
            return

        if isinstance(event, exotel_events.ClearEvent):
            logger.info("[%s] Exotel clear event received.", self.session_id)
            return

        if isinstance(event, exotel_events.DtmfEvent):
            # Sanitized: single digit only, no other DTMF payload stored.
            logger.info("[%s] DTMF digit received: %s",
                        self.session_id, event.digit)
            return

        if isinstance(event, exotel_events.StopEvent):
            logger.info("[%s] Exotel stop event.", self.session_id)
            self.disconnect_reason = "stop_event"
            await self._stop_soon()
            # Don't leave the receive loop parked: closing the WSS
            # wakes it so cleanup runs immediately (Exotel may keep
            # the socket half-open briefly after `stop`).
            await self.transport.close()
            return

    async def _greet(self) -> None:
        try:
            if self.state.state in (AgentState.STOPPING,):
                return  # call ended before the greeting could start
            self.state.transition(AgentState.SPEAKING)
            self.agent.current_reply = GREETING_TEXT
            self.agent.conversation.add_assistant(GREETING_TEXT)
            self.turns.append({"speaker": "assistant", "language": "en-IN",
                               "text": GREETING_TEXT})
            try:
                await self.agent.speak(GREETING_TEXT, "en-IN")
            except Exception as exc:
                logger.warning("[%s] Greeting speak failed (%s): %s",
                               self.session_id, self.active_voice_provider, exc)
                failover_ok = await self.failover_provider(f"greeting_speak_error: {exc}")
                if failover_ok:
                    await self.agent.speak(GREETING_TEXT, "en-IN")
            if self.state.state in (AgentState.SPEAKING,
                                    AgentState.INTERRUPTED):
                self.state.transition(AgentState.LISTENING)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[%s] Greeting failed: %s",
                           self.session_id, type(exc).__name__)

    async def _stop_soon(self) -> None:
        """Set the stop flag so run()'s receive loop exits gracefully."""
        self._stop.set()

    # ------------------------------------------------------------------
    # STT event handlers
    # ------------------------------------------------------------------

    def _on_speech_start(self):
        self._last_activity = time.monotonic()
        if self.state.state is AgentState.SPEAKING:
            self.state.transition(AgentState.INTERRUPTED)
            self.barge_in_count += 1
            self.sink.cancel()
            logger.info("[%s] Barge-in: caller spoke during bot audio.",
                        self.session_id)
        if self.state.state is AgentState.IDLE:
            self.state.transition(AgentState.LISTENING)

    def _on_speech_end(self):
        self._last_activity = time.monotonic()
        self._last_speech_end = time.monotonic()

    def _on_final(self, text: str, language: str):
        self._last_activity = time.monotonic()
        timings = TurnTimings()
        timings.final_transcript = time.monotonic()
        timings.speech_end = self._last_speech_end
        text = self.agent.normalize_transcript(text)  # brand correction
        if self.agent.is_echo(text):
            logger.info("[%s] Suppressed self-echo transcript.",
                        self.session_id)
            return
        language = normalize_language_code(language)
        logger.info("[%s] USER (%s): %s", self.session_id, language, text)
        self.turns.append({"speaker": "user", "language": language,
                           "text": text})
        # Per-call language state (Phase 4.1):
        #  - detected_language: every STT final carries saaras:v4's
        #    auto-detection (language_code=auto); we follow it.
        #  - requested_language: explicit switch requests are sticky for
        #    the rest of the call until another explicit switch (so
        #    code-mixed Hinglish/Tanglish turns don't yank the reply
        #    language back).
        language = normalize_language_code(language)
        if language and language != self.detected_language:
            logger.info("[%s] LANGUAGE DETECTED: %s",
                        self.session_id, language)
            self.detected_language = language
        switch = detect_language_switch(text)
        if switch:
            logger.info("[%s] LANGUAGE SWITCH REQUEST: %s.",
                        self.session_id, switch)
            self.requested_language = switch
            self._fallback_choice_pending = False
        elif (self._fallback_choice_pending and
                len(text.split()) <= 4):
            # Policy A pending: we just asked "Hindi or English?" —
            # treat a short utterance naming a language as the answer.
            picked = match_language_alias(text)
            if picked and supports_tts(picked):
                logger.info("[%s] TTS FALLBACK CHOICE: caller picked %s.",
                            self.session_id, picked)
                self.requested_language = picked
                self._fallback_choice_pending = False
        self.reply_language = (self.requested_language or
                               self.detected_language or "en-IN")
        self._reminded = False
        if any(hint in text.lower() for hint in _HUMAN_HINTS):
            self.human_requested = True  # acknowledged by prompt; no transfer yet
        if self.state.state is AgentState.SPEAKING:
            self.state.transition(AgentState.INTERRUPTED)
            self.barge_in_count += 1
            self.sink.cancel()
        self._turn_queue.put_nowait((text, language, timings))

    # ------------------------------------------------------------------
    # TTS capability routing (Phase 4.1)
    # ------------------------------------------------------------------

    def _route_tts_language(self, target: str) -> "tuple[str, bool]":
        """Return (spoken_language, is_unsupported)."""
        if hasattr(self, "_provider") and self._provider.supports_tts_language(target):
            self.tts_language = target
            return target, False
        if supports_tts(target):
            self.tts_language = target
            return target, False
        if target not in self._tts_unavailable_logged:
            self._tts_unavailable_logged.add(target)
            logger.warning("[%s] TTS_UNAVAILABLE_FOR_LANGUAGE: %s "
                           "(policy=%s, fallback=%s).",
                           self.session_id, target,
                           self.cfg.tts_fallback_policy,
                           self.cfg.tts_fallback_language)
        self.tts_language = self.cfg.tts_fallback_language
        return self.cfg.tts_fallback_language, True

    # ------------------------------------------------------------------
    # turn processing (serialized)
    # ------------------------------------------------------------------

    async def _turn_loop(self):
        while not self._stop.is_set():
            try:
                text, language, timings = await asyncio.wait_for(
                    self._turn_queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            try:
                if self.state.state is not AgentState.STOPPING:
                    self.state.transition(AgentState.PROCESSING)
                    await self._respond(text, language, timings)
            finally:
                self._turn_queue.task_done()

    async def _respond(self, text: str, language: str,
                       timings: TurnTimings) -> None:
        self.agent.timings = timings
        # Effective reply language: sticky caller-requested language
        # wins; otherwise follow the latest STT auto-detection.
        effective = self.reply_language or language or "en-IN"
        tts_language, tts_unsupported = self._route_tts_language(
            effective)
        logger.info("[%s] REPLY LANGUAGE: %s. TTS LANGUAGE: %s.",
                    self.session_id, effective, tts_language)
        try:
            if self.agent.is_ending(text):
                logger.info("[%s] END_CALL DETECTED.", self.session_id)
                reply = CLOSING_TEXT
                self.agent.conversation.add_user(text)
                self.agent.current_reply = reply
                self.state.transition(AgentState.SPEAKING)
                try:
                    await self.agent.speak(reply, tts_language)
                except Exception as exc:
                    logger.warning("[%s] Closing speak failed (%s): %s",
                                   self.session_id, self.active_voice_provider, exc)
                    if await self.failover_provider(f"closing_speak_error: {exc}"):
                        new_tts_lang, _ = self._route_tts_language(tts_language)
                        await self.agent.speak(reply, new_tts_lang)
                self.turns.append({"speaker": "assistant",
                                   "language": effective,
                                   "tts_language": tts_language,
                                   "text": reply})
                self.agent.conversation.add_assistant(reply)
                self.disconnect_reason = "user_end_phrase"
                logger.info("[%s] CLOSING MESSAGE SENT.",
                            self.session_id)
                # Caller heard the closing (finish waited on the mark
                # echo, or timed out). Close the WSS → Exotel advances
                # the flow to the Hangup applet and the call ends.
                logger.info("[%s] WSS CLOSING (bot end-call).",
                            self.session_id)
                await self.transport.close()
                await self._stop_soon()
                return

            if tts_unsupported and self.cfg.tts_fallback_policy == (
                    "ask_hi_en"):
                # Policy A (configurable): Bulbul has no voice for the
                # caller's language, so an LLM answer could not be
                # spoken anyway. Deterministically ask the caller to
                # continue in Hindi or English, spoken in the fallback
                # voice; their short bare answer ("Hindi"/"English") is
                # picked up by the pending-choice handling in _on_final.
                notice = (
                    f"I understand you, but I cannot speak "
                    f"{language_name(effective)} clearly in this "
                    "prototype yet. Shall we continue in Hindi or "
                    "English?")
                self.agent.conversation.add_user(text)
                self.agent.conversation.add_assistant(notice)
                self.agent.current_reply = notice
                self.turns.append({"speaker": "assistant",
                                   "language": effective,
                                   "tts_language": tts_language,
                                   "text": notice})
                self.state.transition(AgentState.SPEAKING)
                try:
                    await self.agent.speak(notice, tts_language)
                except Exception as exc:
                    logger.warning("[%s] Fallback notice speak failed (%s): %s",
                                   self.session_id, self.active_voice_provider, exc)
                    if await self.failover_provider(f"fallback_notice_speak_error: {exc}"):
                        new_tts_lang, _ = self._route_tts_language(tts_language)
                        await self.agent.speak(notice, new_tts_lang)
                self._fallback_choice_pending = True
                # Continue in the fallback voice until the caller picks.
                self.reply_language = tts_language
                return

            reply = await self.agent.generate_reply(
                text, language, reply_language=effective)
            self.agent.current_reply = reply
            self.turn_count += 1
            self.turns.append({"speaker": "assistant",
                               "language": effective,
                               "tts_language": tts_language,
                               "text": reply})
            logger.info("[%s] AI (%s): %s", self.session_id, effective,
                        reply[:120])
            if self.state.state is not AgentState.STOPPING:
                self.state.transition(AgentState.SPEAKING)
            try:
                await self.agent.speak(reply, tts_language)
            except Exception as exc:
                logger.warning("[%s] Reply speak failed (%s): %s",
                               self.session_id, self.active_voice_provider, exc)
                failover_ok = await self.failover_provider(f"reply_speak_error: {exc}")
                if failover_ok:
                    new_tts_lang, _ = self._route_tts_language(effective)
                    await self.agent.speak(reply, new_tts_lang)
                else:
                    return
            self.latencies.append({
                "stt_final_ms": timings.stt_final_ms(),
                "llm_ms": timings.llm_ms(),
                "tts_first_audio_ms": timings.tts_first_audio_ms(),
                "total_ms": timings.total_ms(),
                "first_exotel_media_ms": (
                    round((self.sink.first_send_at - timings.speech_end)
                          * 1000)
                    if (self.sink.first_send_at and timings.speech_end)
                    else None),
            })
            self.sink.first_send_at = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[%s] Turn failed: %s", self.session_id,
                         type(exc).__name__)
            if self.state.state is not AgentState.STOPPING:
                try:
                    self.state.transition(AgentState.ERROR)
                    self.state.transition(AgentState.LISTENING)
                except Exception:
                    pass
                return
        if self.state.state in (AgentState.SPEAKING, AgentState.PROCESSING,
                                AgentState.INTERRUPTED):
            self.state.transition(AgentState.LISTENING)

    # ------------------------------------------------------------------
    # silence watchdog (phone behavior: prompt once, then end)
    # ------------------------------------------------------------------

    async def _silence_watchdog(self):
        timeout = self.cfg.silence_timeout_seconds
        while not self._stop.is_set():
            await asyncio.sleep(1)
            if self.state.state not in (AgentState.LISTENING,
                                        AgentState.IDLE):
                continue
            idle_for = time.monotonic() - self._last_activity
            if not self._reminded and idle_for >= timeout:
                self._reminded = True
                try:
                    tts_language, _ = self._route_tts_language(
                        self.reply_language)
                    self.state.transition(AgentState.SPEAKING)
                    await self.agent.speak(SILENCE_PROMPT_TEXT, tts_language)
                    self.state.transition(AgentState.LISTENING)
                except Exception:
                    pass
            elif self._reminded and idle_for >= timeout * 2:
                try:
                    tts_language, _ = self._route_tts_language(
                        self.reply_language)
                    self.state.transition(AgentState.SPEAKING)
                    await self.agent.speak(CLOSING_TEXT, tts_language)
                    logger.info("[%s] CLOSING MESSAGE SENT (silence "
                                "timeout).", self.session_id)
                except Exception:
                    pass
                self.disconnect_reason = "silence_timeout"
                logger.info("[%s] WSS CLOSING (silence timeout).",
                            self.session_id)
                await self.transport.close()
                await self._stop_soon()
                return

    # ------------------------------------------------------------------
    # logging
    # ------------------------------------------------------------------

    def _save_call_log(self) -> "Path | None":
        try:
            CALL_LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = CALL_LOG_DIR / f"{self.session_id}.json"
            payload = {
                "session_id": self.session_id,
                "call_id": self.call_id,
                "stream_id": self.stream_id,
                "transport": "exotel",
                "connected_at": self.connected_at,
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                # Phase 4.1 language state (kept: "language" mirrors the
                # reply language for earlier consumers of the log).
                "language": self.reply_language,
                "detected_language": self.detected_language,
                "requested_language": self.requested_language,
                "reply_language": self.reply_language,
                "tts_language": self.tts_language,
                # Phase 7.1 dual voice provider metrics
                "initial_voice_provider": getattr(self, "initial_voice_provider", "sarvam"),
                "active_voice_provider": getattr(self, "active_voice_provider", "sarvam"),
                "failover_occurred": getattr(self, "failover_occurred", False),
                "failover_reason": getattr(self, "failover_reason", ""),
                "failover_count": getattr(self, "failover_count", 0),
                "turn_count": self.turn_count,
                "barge_in_count": self.barge_in_count,
                "human_requested": self.human_requested,
                "disconnect_reason": self.disconnect_reason,
                "exotel_sample_rate":
                    self.transport.serializer.exotel_sample_rate,
                "media_events_received": self.transport.media_received,
                "media_events_sent": self.transport.media_sent,
                "turns": self.turns,
                "latencies": self.latencies,
            }
            path.write_text(json.dumps(payload, indent=2,
                                       ensure_ascii=False))
            return path
        except Exception as exc:
            logger.error("[%s] Failed to save call log: %s",
                         self.session_id, type(exc).__name__)
            return None
