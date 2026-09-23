"""Phase 4 stabilization tests — audio pacing/integrity, language
switching, end-call intent, session cleanup, sequential calls.

All mock-only: no Exotel, no ngrok, no Sarvam credits.
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
from agent.state import AgentState  # noqa: E402
from agent.voice_agent import (  # noqa: E402
    CLOSING_TEXT,
    VoiceAgent,
    detect_language_switch,
)
from telephony import session as session_module  # noqa: E402
from telephony.serializer import ExotelSerializer, resample_pcm16  # noqa: E402
from transports.exotel import ExotelTransport  # noqa: E402

from tests.test_phase4_exotel import (  # noqa: E402
    DUMMY_KEY,
    FakeSTT,
    FakeTTS,
    FakeWebSocket,
    _cfg,
    _chat_client,
    _make_session,
    _media_msg,
    _start_msg,
)


# ---------------------------------------------------------------------
# Fix C — deterministic end-call intent
# ---------------------------------------------------------------------

class TestEndCallIntent:
    @pytest.mark.parametrize("phrase", [
        "bye", "goodbye", "end the call", "cut the call",
        "cut this call", "disconnect the call", "hang up",
        "that's all", "thank you that's all", "nothing else",
        "you can disconnect", "can you cut the call",
        "call cut pannunga", "call-a cut pannunga",
        "phone-a cut pannunga",
    ])
    def test_end_phrases_detected(self, phrase):
        assert VoiceAgent.is_ending(phrase)

    @pytest.mark.parametrize("phrase", [
        "My call got disconnected yesterday and I need help",
        "I want to continue the call",
        "can you help me with my account",
    ])
    def test_non_endings_not_detected(self, phrase):
        assert not VoiceAgent.is_ending(phrase)


# ---------------------------------------------------------------------
# Fix B — deterministic language switching
# ---------------------------------------------------------------------

class TestLanguageSwitchDetection:
    @pytest.mark.parametrize("text,code", [
        ("Can you speak in Tamil?", "ta-IN"),
        ("Speak Tamil.", "ta-IN"),
        ("Tamil please, can we switch?", "ta-IN"),
        ("Can we continue in Hindi?", "hi-IN"),
        ("Hindi mein baat karo.", "hi-IN"),
        ("Please switch to Hindi", "hi-IN"),
        ("Can you switch back to English?", "en-IN"),
        ("தமிழில் பேச முடியுமா?", "ta-IN"),
    ])
    def test_switch_requests(self, text, code):
        assert detect_language_switch(text) == code

    @pytest.mark.parametrize("text", [
        "I am learning Tamil on Zhatura.",
        "Do you have Tamil chess lessons?",
        "My son studies in a Hindi medium school.",
        "The English course is good.",
    ])
    def test_no_false_switches(self, text):
        assert detect_language_switch(text) is None

    def test_session_switches_language_state(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(),
                                    tmp_path)
            try:
                session._on_final("Can you speak in Tamil?", "en-IN")
                assert session.language == "ta-IN"
                # caller then actually speaks Tamil; STT auto-detects
                # and the session follows it
                session._on_final("என் பாடம் தெரியவில்லை", "ta-IN")
                assert session.language == "ta-IN"
                session._on_final("Can you switch back to English?",
                                  "en-IN")
                assert session.language == "en-IN"
            finally:
                await session.shutdown()

        asyncio.run(scenario())

    def test_respond_uses_requested_language(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(),
                                    tmp_path)
            try:
                session.language = "ta-IN"
                session.state.transition(AgentState.LISTENING)
                session.state.transition(AgentState.PROCESSING)
                timings = session_module.TurnTimings()
                await session._respond("ok continue", "en-IN", timings)
                assert session.tts.last_language == "ta-IN"
            finally:
                await session.shutdown()

        asyncio.run(scenario())


# ---------------------------------------------------------------------
# Fix A — outbound audio: fixed frames, real-time pacing, integrity
# ---------------------------------------------------------------------

class CapturingTransport:
    """Sink-facing transport: records PCM frames, clear and marks."""

    def __init__(self):
        self.frames: "list[tuple[float, bytes]]" = []
        self.clears = 0
        self.marks: list[str] = []

    async def send_audio(self, pcm: bytes, rate: int):
        self.frames.append((time.monotonic(), bytes(pcm)))

    async def clear_audio(self):
        self.clears += 1

    async def send_mark(self, name: str):
        self.marks.append(name)


def _run_sink_test(coro):
    """Run async sink test body on a fresh loop."""
    return asyncio.run(coro)


def _wait_for(predicate, timeout=5.0) -> bool:
    """Poll `predicate` (sync tests) until true or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


def _decode_identity(data, _rate):
    return np.frombuffer(data, dtype=np.int16)


class TestAudioPacing:
    def test_fixed_frames_and_pacing_and_integrity(self, monkeypatch):
        monkeypatch.setattr(session_module, "_MARK_TIMEOUT_S", 0.2)

        async def body():
            monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                                _decode_identity)
            transport = CapturingTransport()
            sink = session_module.TelephonyAudioSink(
                transport, asyncio.get_event_loop(), 16000, frame_ms=40)
            sink.start_pacer()
            # 0.48 s of deterministic PCM (ramp pattern), fed as MP3
            # chunks would be: 3 chunks of 160 ms.
            expected = (np.arange(int(16000 * 0.48)) % 2000 - 1000).astype(
                np.int16)
            data = expected.tobytes()
            t0 = time.monotonic()
            loop = asyncio.get_event_loop()
            for i in range(0, len(data), int(16000 * 0.16) * 2):
                sink.feed_mp3_chunk(data[i:i + int(16000 * 0.16) * 2])
            # finish() is a blocking worker-thread call in production —
            # never run it on the loop thread.
            await loop.run_in_executor(None, sink.finish)
            elapsed = time.monotonic() - t0
            sink.close()
            await sink.stop()

            payload = b"".join(frame for _, frame in transport.frames)
            # integrity: every byte, in order, none lost or duplicated
            assert payload == data
            # fixed frame size (16000*2*0.04 = 1280 B); only the last
            # frame is the partial tail
            sizes = [len(frame) for _, frame in transport.frames]
            assert all(size == 1280 for size in sizes[:-1])
            # pacing: 480 ms of audio cannot be sent in a burst
            # (finish adds up to _MARK_TIMEOUT_S for the mark echo,
            # which this capturing transport does not echo back)
            assert elapsed >= 0.35
            assert elapsed < 0.48 + 0.2 + 1.0
            return transport, elapsed

        _run_sink_test(body())

    def test_barge_in_flushes_buffer_and_clears(self, monkeypatch):
        async def body():
            monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                                _decode_identity)
            transport = CapturingTransport()
            sink = session_module.TelephonyAudioSink(
                transport, asyncio.get_event_loop(), 16000, frame_ms=40)
            sink.start_pacer()
            data = b"\x00\x01" * 16000 * 3  # ~3 s of audio
            sink.feed_mp3_chunk(data)
            await asyncio.sleep(0.2)  # a few frames have been sent
            sent_before = len(transport.frames)
            sink.cancel()  # barge-in
            assert sink._buffer_depth() == 0
            await asyncio.sleep(0.3)
            # a short tail from the in-flight frame is tolerated,
            # but the buffered ~2.5 s must NOT drain after cancel
            assert len(transport.frames) - sent_before <= 2
            assert transport.clears >= 1
            # finish must return immediately when cancelled
            sink.cancel()
            await asyncio.get_event_loop().run_in_executor(
                None, sink.finish)
            sink.close()
            await sink.stop()

        _run_sink_test(body())

    def test_partial_tail_frame_is_flushed(self, monkeypatch):
        monkeypatch.setattr(session_module, "_MARK_TIMEOUT_S", 0.2)

        async def body():
            monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                                _decode_identity)
            transport = CapturingTransport()
            sink = session_module.TelephonyAudioSink(
                transport, asyncio.get_event_loop(), 16000, frame_ms=100)
            sink.start_pacer()
            # 130 ms total: one full 100 ms frame + 30 ms tail
            data = b"\x05\x00" * int(16000 * 0.130)
            sink.feed_mp3_chunk(data)
            await asyncio.get_event_loop().run_in_executor(
                None, sink.finish)
            sink.close()
            await sink.stop()
            sizes = [len(f) for _, f in transport.frames]
            assert sizes[-1] == 2 * int(16000 * 0.130) - 3200
            assert sum(sizes) == len(data)

        _run_sink_test(body())

    def test_serializer_round_trip_reconstructs_wav(self):
        """Known PCM → Exotel media frames → reconstructed PCM
        (§20 telephony audio self-test)."""
        rate = 16000
        samples = (np.sin(np.arange(rate) * 0.05) * 12000).astype(np.int16)
        data = samples.tobytes()  # exactly 1 s
        serializer = ExotelSerializer(
            stream_sid="s1", exotel_sample_rate=rate)
        messages = serializer.media_messages(data, rate)
        assert len(messages) == 10  # 100 ms per frame
        out = b"".join(
            base64.b64decode(json.loads(m)["media"]["payload"])
            for m in messages)
        assert out == data
        assert len(out) // 2 == rate
        # duration: 1.0 s, no gaps, no duplication
        assert np.array_equal(np.frombuffer(out, np.int16), samples)

    def test_resample_16k_to_8k_halves_samples(self):
        pcm = (np.arange(16000) % 1000).astype(np.int16).tobytes()
        out = resample_pcm16(pcm, 16000, 8000)
        assert abs(len(np.frombuffer(out, np.int16)) - 8000) <= 2


# ---------------------------------------------------------------------
# Fix C/D — end-call flow closes WSS; cleanup idempotent; sequential
# calls; duplicate session defense
# ---------------------------------------------------------------------

class TestEndCallFlow:
    def test_cut_phrase_closes_socket(self, monkeypatch, tmp_path):
        async def scenario():
            ws = FakeWebSocket()
            session = _make_session(monkeypatch, ws, tmp_path)
            await session.transport.start()  # connected state, as run()
            session.language = "en-IN"
            session.state.transition(AgentState.LISTENING)
            session.state.transition(AgentState.PROCESSING)
            timings = session_module.TurnTimings()
            await session._respond("Can you cut the call?", "en-IN",
                                   timings)
            assert session.disconnect_reason == "user_end_phrase"
            assert session.tts.spoken[-1] == CLOSING_TEXT
            assert ws.closed is True          # → Exotel Hangup applet
            assert session.transport.connected is False
            await session.shutdown()
            await session.shutdown()  # idempotent

        asyncio.run(scenario())

    def test_full_call_ends_on_cut_phrase(self, monkeypatch, tmp_path):
        async def scenario():
            ws = FakeWebSocket(inbound=[
                '{"event": "connected"}',
                _start_msg("sid-cut", "call-cut"),
            ], delay_s=0.02)
            session = _make_session(monkeypatch, ws, tmp_path)
            run_task = asyncio.create_task(session.run())
            await asyncio.sleep(0.15)

            async def caller_talks():
                await asyncio.sleep(0.6)  # let the greeting get going
                session._on_final("Can you cut the call?", "en-IN")

            talker = asyncio.create_task(caller_talks())
            await asyncio.wait_for(run_task, timeout=20)
            await talker
            assert ws.closed is True
            assert session.disconnect_reason == "user_end_phrase"
            # cleanup fully ran
            assert session.stt.stopped is True
            assert session.tts.is_open is False

        asyncio.run(scenario())

    def test_shutdown_is_idempotent(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(),
                                    tmp_path)
            await session.transport.start()
            await session.shutdown()
            await session.shutdown()  # no crash, no double-finalize
            logs = list(tmp_path.glob("call-*.json"))
            assert len(logs) == 1  # call log written exactly once

        asyncio.run(scenario())


class TestSequentialCalls:
    """Three sequential calls through the real FastAPI app with faked
    STT/TTS — active_calls must return to zero after each (§13, §14)."""

    def test_three_sequential_calls_cleanup(self, monkeypatch, tmp_path):
        monkeypatch.setattr(session_module, "RealtimeSTT", FakeSTT)
        monkeypatch.setattr(session_module, "StreamingTTS", FakeTTS)
        monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                            lambda _b, rate: np.zeros(int(rate * 0.1),
                                                      dtype=np.int16))
        monkeypatch.setattr(session_module, "CALL_LOG_DIR", tmp_path)
        monkeypatch.setattr(session_module, "_MARK_TIMEOUT_S", 2.0)

        import phase4_exotel_server as server_module
        app = server_module.create_app(_cfg())

        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)
        health = lambda: client.get("/health").json()["active_calls"]
        for i in range(1, 4):
            with client.websocket_connect("/ws?sample-rate=16000") as ws:
                ws.send_text('{"event":"connected"}')
                ws.send_text(_start_msg(f"stream-{i}", f"call-{i}"))
                assert _wait_for(lambda: health() == 1), \
                    f"active_calls never reached 1 during call {i}"
                ws.send_text(json.dumps(
                    {"event": "stop", "call_sid": f"call-{i}"}))
            assert _wait_for(lambda: health() == 0), \
                f"active_calls did not return to 0 after call {i}"
        assert not app.state.sessions  # registry cleaned
        logs = list(tmp_path.glob("call-*.json"))
        # greeting + stop per call; one log per call minimum
        assert len(logs) >= 3

    def test_duplicate_stream_sid_shuts_down_stale(self, monkeypatch,
                                                   tmp_path):
        monkeypatch.setattr(session_module, "RealtimeSTT", FakeSTT)
        monkeypatch.setattr(session_module, "StreamingTTS", FakeTTS)
        monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                            lambda _b, rate: np.zeros(int(rate * 0.1),
                                                      dtype=np.int16))
        monkeypatch.setattr(session_module, "CALL_LOG_DIR", tmp_path)
        monkeypatch.setattr(session_module, "_MARK_TIMEOUT_S", 2.0)

        import phase4_exotel_server as server_module
        app = server_module.create_app(_cfg())
        from fastapi.testclient import TestClient
        client = TestClient(app, raise_server_exceptions=False)

        ws1 = client.websocket_connect("/ws?sample-rate=16000")
        ws1.__enter__()
        ws1.send_text(_start_msg("dup-sid", "call-old"))
        assert _wait_for(lambda: app.state.sessions.get("dup-sid")
                         is not None)
        old_session = app.state.sessions.get("dup-sid")

        ws2 = client.websocket_connect("/ws?sample-rate=16000")
        ws2.__enter__()
        ws2.send_text(_start_msg("dup-sid", "call-new"))
        # stale session finalized, fresh session owns the registry entry
        assert _wait_for(lambda: old_session._finalized)
        assert app.state.sessions.get("dup-sid") is not old_session

        ws2.send_text(json.dumps({"event": "stop",
                                  "call_sid": "call-new"}))
        # In production, Exotel answers our server-side close with a
        # disconnect, waking the stale session's parked receive. The
        # TestClient's in-memory transport needs the client to close
        # explicitly to mirror that — and close() raises if the server
        # already closed it, which is exactly the success case.
        def _client_close(ws):
            try:
                ws.close()
            except Exception:
                pass

        _client_close(ws1)
        health = lambda: client.get("/health").json()["active_calls"]
        assert _wait_for(lambda: health() == 0
                         and not app.state.sessions, timeout=8)
        _client_close(ws2)
