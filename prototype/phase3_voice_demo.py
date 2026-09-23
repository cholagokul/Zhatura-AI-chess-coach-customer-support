"""Zhatura AI Customer Care — Phase 3 LIVE voice demo.

⚠ Makes REAL Sarvam API calls and uses the local microphone/speaker.
Never run under pytest.

    python prototype/phase3_voice_demo.py

Headphones are recommended for clean turns (the mic may hear the
speaker without them — echo suppression is heuristic-only here).

A --selftest mode drives the pipeline with generated WAV files instead
of the microphone, for automated live verification.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
import time
import uuid
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from agent.conversation import Conversation  # noqa: E402
from agent.state import AgentState, AgentStateMachine  # noqa: E402
from agent.voice_agent import (  # noqa: E402
    CLOSING_TEXT,
    SILENCE_PROMPT_TEXT,
    TurnTimings,
    VoiceAgent,
)
from speech.microphone import MicrophoneError, MicrophoneStreamer  # noqa: E402
from speech.realtime_stt import RealtimeSTT, RealtimeSTTError  # noqa: E402
from speech.streaming_tts import (  # noqa: E402
    SpeakerPlayer,
    StreamingTTS,
    select_tts_language,
)

LOG = logging.getLogger("phase3.demo")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONVO_LOG_DIR = PROJECT_ROOT / "prototype" / "logs" / "conversations"


# ---------------------------------------------------------------------
# Session transcript logging
# ---------------------------------------------------------------------

class TranscriptLog:
    def __init__(self):
        self.session_id = f"local-{uuid.uuid4().hex[:8]}"
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.turns: list[dict] = []
        self.latencies: list[dict] = []

    def add(self, speaker: str, language: str, text: str):
        self.turns.append({"speaker": speaker, "language": language, "text": text})

    def add_latency(self, timings: "TurnTimings"):
        self.latencies.append({
            "stt_final_ms": timings.stt_final_ms(),
            "llm_ms": timings.llm_ms(),
            "tts_first_audio_ms": timings.tts_first_audio_ms(),
            "total_ms": timings.total_ms(),
        })

    def save(self):
        CONVO_LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = CONVO_LOG_DIR / f"{self.session_id}.json"
        payload = {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "turns": self.turns,
            "latencies": self.latencies,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        LOG.info("Transcript saved to %s", path)
        return path


# ---------------------------------------------------------------------
# Audio file feeder (selftest mode)
# ---------------------------------------------------------------------

async def feed_wav_to_stt(stt: RealtimeSTT, wav_paths: "list[Path]",
                          chunk_ms: int = 100, realtime_pacing: bool = True,
                          stop_when=None):
    """Stream WAV files (any rate) as 16 kHz linear16 into the STT socket."""
    for wav_path in wav_paths:
        with wave.open(str(wav_path), "rb") as w:
            frames = w.readframes(w.getnframes())
            rate = w.getframerate()
            channels = w.getnchannels()
            width = w.getsampwidth()
        pcm16 = _to_pcm16_mono(frames, width, channels)
        pcm16 = _resample(pcm16, rate, 16000)
        chunk = 3200  # 100 ms @16kHz int16
        silence = b"\x00\x00" * 3200 * 6  # close the VAD turn
        for block in (pcm16, silence):
            for i in range(0, len(block), chunk):
                if stop_when and stop_when():
                    return
                await stt.send_audio(block[i:i + chunk])
                if realtime_pacing:
                    await asyncio.sleep(chunk_ms / 1000)
    await stt.flush()


def _to_pcm16_mono(frames: bytes, width: int, channels: int) -> np.ndarray:
    if width == 2:
        a = np.frombuffer(frames, dtype=np.int16)
    elif width == 4:
        a = (np.frombuffer(frames, dtype=np.int32) / 65536).astype(np.int16)
    else:
        a = (np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) << 8
    if channels > 1:
        a = a.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return a


def _resample(pcm: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return pcm
    a = pcm.astype(np.float32)
    idx = np.linspace(0, len(a) - 1, int(len(a) * dst / src))
    return np.interp(idx, np.arange(len(a)), a).astype(np.int16)


# ---------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------

class LiveVoiceSession:
    """Wires mic → realtime STT → voice agent → streaming TTS → speaker."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.state = AgentStateMachine()
        self.stt = RealtimeSTT(cfg=cfg)
        self.tts = StreamingTTS(cfg=cfg, client=self.stt._client)
        self.player = SpeakerPlayer(sample_rate=cfg.tts_stream_sample_rate)
        self.agent = VoiceAgent(
            cfg=cfg,
            conversation=Conversation.from_prompt_file(
                max_turns=cfg.max_conversation_turns),
            chat_client=self.stt._client,
            tts=self.tts,
            player=self.player,
        )
        self.mic: "MicrophoneStreamer | None" = None
        self.mic_queue = None
        self.transcript_log = TranscriptLog()
        self._silence_task: "asyncio.Task | None" = None
        self._turn_queue = asyncio.Queue()
        self._turn_worker: "asyncio.Task | None" = None
        self._last_speech_end: "float | None" = None
        self._last_activity = time.monotonic()
        self._reminded = False
        self._stop = asyncio.Event()

        # Wire STT events
        self.stt.on_speech_start = self._on_speech_start
        self.stt.on_speech_end = self._on_speech_end
        self.stt.on_partial = self._on_partial
        self.stt.on_final = self._on_final
        self.stt.on_error = self._on_stt_error

    # -- STT event handlers (sync callbacks from rx loop) --------------

    def _touch(self):
        self._last_activity = time.monotonic()

    def _on_speech_start(self):
        self._touch()
        if self.state.state is AgentState.SPEAKING:
            self.state.transition(AgentState.INTERRUPTED)
            self.player.cancel()
            print("\n[INTERRUPTED — user spoke while AI was talking]")
        if self.state.state is AgentState.IDLE:
            self.state.transition(AgentState.LISTENING)

    def _on_speech_end(self):
        self._touch()
        self._last_speech_end = time.monotonic()

    def _on_partial(self, text: str):
        self._touch()
        print(f"\r\033[KUSER [partial]: {text}", end="", flush=True)

    def _on_final(self, text: str, language: str):
        self._touch()
        # Fresh per-turn timing measurements (real values only). Travels
        # with the queued item so concurrent finals can't stomp a turn
        # that is still being processed.
        timings = TurnTimings()
        timings.final_transcript = time.monotonic()
        timings.speech_end = self._last_speech_end
        text = self.agent.normalize_transcript(text)  # brand correction
        if self.agent.is_echo(text):
            LOG.info("Suppressed self-echo transcript.")
            return
        print(f"\nUSER: {text}  ({language})")
        self.transcript_log.add("user", language, text)
        self._reminded = False
        if self.state.state is AgentState.SPEAKING:
            self.state.transition(AgentState.INTERRUPTED)
            self.player.cancel()
        # Serialize turns: one in flight, the rest queued in order.
        self._turn_queue.put_nowait((text, language, timings))

    def _on_stt_error(self, message: str):
        LOG.error("STT error event: %s", message)

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

    # -- conversation turns ---------------------------------------------

    async def _respond(self, text: str, language: str, timings: "TurnTimings"):
        # Processing is serialized, so this object is exclusively ours.
        self.agent.timings = timings
        reply = ""
        try:
            if self.agent.is_ending(text):
                reply = CLOSING_TEXT
                self.agent.conversation.add_user(text)
                self.agent.current_reply = reply
                self.state.transition(AgentState.SPEAKING)
                await self.agent.speak(reply, select_tts_language(language))
                self.transcript_log.add("assistant", language, reply)
                self.agent.conversation.add_assistant(reply)
                print(f"AI: {reply}")
                await self.shutdown(reason="user ended conversation")
                return

            reply = await self.agent.generate_reply(text, language)
            self.agent.current_reply = reply
            self.transcript_log.add("assistant", language, reply)
            print(f"AI: {reply}")
            # Only SPEAKING here — barge-in detection keys off this state.
            self.state.transition(AgentState.SPEAKING)
            await self.agent.speak(reply, select_tts_language(language))
            print("\nLatency:")
            print(timings.summary())
            self.transcript_log.add_latency(timings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.error("Turn failed: %s", exc)
            print(f"\n[Turn error: {exc}]")
            if self.state.state is not AgentState.STOPPING:
                self.state.transition(AgentState.ERROR)
                self.state.transition(AgentState.LISTENING)
                return
        if self.state.state in (AgentState.SPEAKING, AgentState.PROCESSING,
                                AgentState.INTERRUPTED):
            self.state.transition(AgentState.LISTENING)
        print("\n[LISTENING]")

    # -- silence watchdog -------------------------------------------------

    async def _silence_watchdog(self):
        timeout = self.cfg.silence_timeout_seconds
        while not self._stop.is_set():
            await asyncio.sleep(1)
            if self.state.state not in (AgentState.LISTENING, AgentState.IDLE):
                continue
            idle_for = time.monotonic() - self._last_activity
            if not self._reminded and idle_for >= timeout:
                self._reminded = True
                LOG.info("Silence timeout reached — prompting user.")
                try:
                    self.state.transition(AgentState.SPEAKING)
                    await self.agent.speak(SILENCE_PROMPT_TEXT, "en-IN")
                    self.state.transition(AgentState.LISTENING)
                    print(f"\nAI: {SILENCE_PROMPT_TEXT}")
                    print("\n[LISTENING]")
                except Exception as exc:
                    LOG.error("Silence prompt failed: %s", exc)
            elif self._reminded and idle_for >= timeout * 2:
                LOG.info("Second silence timeout — ending session.")
                try:
                    self.state.transition(AgentState.SPEAKING)
                    await self.agent.speak(CLOSING_TEXT, "en-IN")
                except Exception:
                    pass
                await self.shutdown(reason="prolonged silence")
                return

    # -- lifecycle ----------------------------------------------------------

    async def start(self, selftest_wavs: "list[Path] | None" = None):
        await self.stt.start()
        await self.tts.open(self.cfg.tts_language)
        self.state.transition(AgentState.LISTENING)
        self._silence_task = asyncio.create_task(self._silence_watchdog())
        self._turn_worker = asyncio.create_task(self._turn_loop())

        if self.cfg.auto_greeting:
            self.state.transition(AgentState.SPEAKING)
            greeting = ("Hello, welcome to Zhatura customer support. "
                        "How can I help you today?")
            self.agent.current_reply = greeting
            self.agent.conversation.add_assistant(greeting)
            await self.agent.speak(greeting, "en-IN")
            self.transcript_log.add("assistant", "en-IN", greeting)
            print(f"AI: {greeting}")
            self.state.transition(AgentState.LISTENING)

        print("\n[LISTENING]")

        if selftest_wavs:
            await feed_wav_to_stt(self.stt, selftest_wavs,
                                  stop_when=lambda: self._stop.is_set())
            # Let the turn worker drain what the feeder enqueued.
            try:
                await asyncio.wait_for(self._turn_queue.join(), 120)
            except (TimeoutError, asyncio.CancelledError):
                pass
            await asyncio.sleep(1)
        else:
            self.mic = MicrophoneStreamer(self.cfg.microphone_sample_rate)
            self.mic_queue = self.mic.start(asyncio.get_event_loop())
            while not self._stop.is_set():
                chunk = await self.mic_queue.get()
                if self.state.state is not AgentState.STOPPING:
                    await self.stt.send_audio(chunk)

    async def shutdown(self, reason: str = "user"):
        if self.state.state is AgentState.STOPPING:
            return
        self._stop.set()
        try:
            self.state.transition(AgentState.STOPPING)
        except Exception:
            pass
        LOG.info("Shutting down (%s).", reason)
        if self._silence_task:
            self._silence_task.cancel()
            try:
                await self._silence_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._turn_worker:
            self._turn_worker.cancel()
            try:
                await self._turn_worker
            except (asyncio.CancelledError, Exception):
                pass
        if self.mic:
            self.mic.stop()
        self.player.close()
        await self.stt.stop()
        await self.tts.close()
        path = self.transcript_log.save()
        print(f"\nConversation transcript: {path}")


async def run(selftest_wavs: "list[Path] | None" = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    print("=" * 50)
    print("ZHATURA AI CUSTOMER CARE — LIVE VOICE PROTOTYPE")
    print("=" * 50)

    try:
        cfg = config.load_config()
    except config.ConfigurationError as exc:
        print(exc)
        return 1

    if selftest_wavs is None:
        from speech.microphone import check_microphone_available

        ok, message = check_microphone_available()
        if not ok:
            print(f"\nMicrophone: NOT READY\n{message}")
            return 1
        print("\nSarvam: configured")
        print("Microphone: READY")
        print("Speaker: READY")
        print("Realtime STT: connecting...")
    else:
        print("\nSELFTEST MODE (WAV-driven, no microphone)")

    session = LiveVoiceSession(cfg)
    try:
        await session.start(selftest_wavs)
    except RealtimeSTTError as exc:
        print(f"\nRealtime STT failed: {exc}")
        return 1
    except MicrophoneError as exc:
        print(f"\n{exc}")
        return 1
    except asyncio.CancelledError:
        pass
    finally:
        if session.state.state is not AgentState.STOPPING:
            await session.shutdown(reason="demo exit")
    print("\nSession ended.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 live voice demo.")
    parser.add_argument("--selftest", action="store_true",
                        help="Drive the pipeline with WAV files (no mic).")
    parser.add_argument("--wavs", nargs="+", type=Path, default=None,
                        help="Custom WAV list for --selftest mode.")
    args = parser.parse_args()

    wavs = None
    if args.selftest or args.wavs:
        if args.wavs:
            wavs = list(args.wavs)
        else:
            base = PROJECT_ROOT / "audio_samples" / "sarvam"
            wavs = [
                base / "english" / "welcome.wav",
                base / "english" / "account_help.wav",
                base / "english" / "problem.wav",
                base / "terminology" / "brand_zhatura_ai.wav",
                base / "english" / "human_transfer.wav",
            ]
        missing = [str(w) for w in wavs if not w.exists()]
        if missing:
            print("Selftest WAVs missing:", missing)
            return 1

    try:
        return asyncio.run(run(wavs))
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
