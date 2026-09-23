"""Phase 4 tests — Exotel telephony transport, events, sessions.

All Exotel WebSockets, Sarvam calls and audio hardware are mocked
or faked. No API credits are consumed, no network is touched.
"""

import asyncio
import base64
import json
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
from agent.state import AgentState  # noqa: E402
from agent.voice_agent import TurnTimings  # noqa: E402
from telephony import exotel_events as ev  # noqa: E402
from telephony import session as session_module  # noqa: E402
from telephony.serializer import ExotelSerializer, resample_pcm16  # noqa: E402
from transports.exotel import (  # noqa: E402
    MAX_MESSAGE_BYTES,
    ExotelTransport,
    TransportClosed,
)

DUMMY_KEY = "test-dummy-key-not-a-real-secret"


def _cfg(**overrides):
    values = dict(sarvam_api_key=DUMMY_KEY, env_file_found=True,
                  exotel_audio_sample_rate=16000)
    values.update(overrides)
    return config.Config(**values)


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------

class FakeDisconnect(Exception):
    pass


class FakeWebSocket:
    """In-memory stand-in for a Starlette WebSocket.

    ``None`` in the inbound queue simulates a client disconnect.
    Marks are echoed back like Exotel does after playback.
    """

    def __init__(self, inbound=(), delay_s: float = 0.0):
        self._in: asyncio.Queue = asyncio.Queue()
        for m in inbound:
            self._in.put_nowait(m)
        self.sent: list[str] = []
        self.closed = False
        self._delay = delay_s

    async def receive_text(self):
        if self._delay:
            # Pace inbound events like a real call so background tasks
            # (greeting, turns) get event-loop time between messages.
            await asyncio.sleep(self._delay)
        msg = await self._in.get()
        if msg is None:
            raise FakeDisconnect()
        return msg

    async def send_text(self, msg: str):
        self.sent.append(msg)
        try:
            data = json.loads(msg)
        except ValueError:
            return
        if data.get("event") == "mark":
            # Simulate Exotel's mark echo once audio has played out.
            self._in.put_nowait(json.dumps(
                {"event": "mark", "mark": {"name": data["mark"]["name"]}}))

    async def close(self):
        self.closed = True
        # A real WebSocket close wakes any pending receive — mirror it
        # so receive loops unblock and finalize.
        self._in.put_nowait(None)

    def sent_events(self):
        return [json.loads(m) for m in self.sent]


class FakeSTT:
    """Scriptable realtime STT double."""

    def __init__(self, cfg=None, client=None):
        self._client = client
        self.received: list[bytes] = []
        self.started = False
        self.stopped = False
        self.on_speech_start = lambda: None
        self.on_speech_end = lambda: None
        self.on_partial = lambda _t: None
        self.on_final = lambda _t, _l: None
        self.on_error = lambda _m: None

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_audio(self, pcm: bytes):
        self.received.append(pcm)

    async def flush(self):
        pass


class FakeTTS:
    def __init__(self, cfg=None, client=None):
        self.is_open = False
        self.spoken: list[str] = []

    async def open(self, language_code="en-IN"):
        self.is_open = True

    async def close(self):
        self.is_open = False

    async def configure(self, language_code):
        pass

    async def synthesize(self, text, language_code, on_audio_chunk):
        self.spoken.append(text)
        self.last_language = language_code
        await on_audio_chunk(b"fake-mp3-chunk")


def _chat_client(reply="I can help with that."):
    client = mock.AsyncMock()
    response = mock.Mock()
    choice = mock.Mock()
    choice.message.content = reply
    response.choices = [choice]
    client.chat.completions.return_value = response
    return client


def _make_session(monkeypatch, ws=None, tmp_path=None):
    """Build a CallSession with STT/TTS fakes patched in.

    Must be called inside a running event loop (Python 3.14)."""
    monkeypatch.setattr(session_module, "RealtimeSTT", FakeSTT)
    monkeypatch.setattr(session_module, "StreamingTTS", FakeTTS)
    monkeypatch.setattr(session_module, "decode_mp3_to_pcm16",
                        lambda _b, rate: np.zeros(int(rate * 0.1),
                                                  dtype=np.int16))
    if tmp_path is not None:
        monkeypatch.setattr(session_module, "CALL_LOG_DIR", tmp_path)
    # Unit tests have no receive loop draining mark echoes; bound the
    # playback-wait so tests stay fast and deterministic.
    monkeypatch.setattr(session_module, "_MARK_TIMEOUT_S", 2.0)
    transport = ExotelTransport(ws or FakeWebSocket(),
                                exotel_sample_rate=16000)
    return session_module.CallSession(_cfg(), transport,
                                      sarvam_client=_chat_client())


def _media_msg(pcm: bytes) -> str:
    return json.dumps({"event": "media", "media": {
        "payload": base64.b64encode(pcm).decode()}})


def _start_msg(stream="sid-1", call="call-1") -> str:
    return json.dumps({"event": "start", "start": {
        "stream_sid": stream, "call_sid": call,
        "custom_parameters": {"foo": "bar"}}})


# ---------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------

class TestEventParsing:
    def test_connected(self):
        e = ev.parse_message('{"event": "connected"}')
        assert isinstance(e, ev.ConnectedEvent)

    def test_start_full(self):
        e = ev.parse_message(_start_msg())
        assert isinstance(e, ev.StartEvent)
        assert e.stream_sid == "sid-1"
        assert e.call_sid == "call-1"
        assert e.custom_param_keys == ("foo",)
        assert e.custom_params == {"foo": "bar"}

    def test_start_flat_shape(self):
        e = ev.parse_message('{"event": "start", "stream_sid": "s9"}')
        assert e.stream_sid == "s9"

    def test_start_missing_stream_sid(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message('{"event": "start"}')

    def test_media_decodes_base64(self):
        pcm = b"\x01\x00" * 160
        e = ev.parse_message(_media_msg(pcm))
        assert isinstance(e, ev.MediaEvent)
        assert e.payload == pcm

    def test_media_missing_payload(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message('{"event": "media", "media": {}}')

    def test_media_bad_base64(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message('{"event": "media", "media": '
                             '{"payload": "!!!not-base64!!!"}}')

    def test_dtmf(self):
        e = ev.parse_message('{"event": "dtmf", "dtmf": {"digit": "5"}}')
        assert isinstance(e, ev.DtmfEvent)
        assert e.digit == "5"

    def test_dtmf_missing_digit(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message('{"event": "dtmf", "dtmf": {}}')

    def test_mark(self):
        e = ev.parse_message(
            '{"event": "mark", "mark": {"name": "utterance-1"}}')
        assert isinstance(e, ev.MarkEvent)
        assert e.name == "utterance-1"

    def test_clear(self):
        assert isinstance(ev.parse_message('{"event": "clear"}'),
                          ev.ClearEvent)

    def test_stop(self):
        e = ev.parse_message('{"event": "stop", "call_sid": "c1"}')
        assert isinstance(e, ev.StopEvent)
        assert e.call_sid == "c1"

    def test_invalid_json(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message("{not json")

    def test_non_object_json(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message("[1, 2, 3]")

    def test_missing_event_field(self):
        with pytest.raises(ev.EventsError):
            ev.parse_message('{"foo": "bar"}')

    def test_unknown_event(self):
        e = ev.parse_message('{"event": "something_else"}')
        assert isinstance(e, ev.UnknownEvent)
        assert e.name == "something_else"

    def test_custom_param_values_truncated(self):
        long_value = "x" * 5000
        msg = json.dumps({"event": "start", "stream_sid": "s",
                          "custom_parameters": {"note": long_value}})
        e = ev.parse_message(msg)
        assert len(e.custom_params["note"]) <= 256

    def test_bytes_input(self):
        e = ev.parse_message(b'{"event": "connected"}')
        assert isinstance(e, ev.ConnectedEvent)


# ---------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------

class TestSerializer:
    def test_media_message_shape(self):
        s = ExotelSerializer(stream_sid="sid-x", exotel_sample_rate=8000)
        # 100 ms of 16 kHz int16 mono = 3200 bytes
        msgs = s.media_messages(b"\x00\x00" * 1600, 16000)
        assert len(msgs) >= 1
        data = json.loads(msgs[0])
        assert data["event"] == "media"
        assert data["stream_sid"] == "sid-x"
        decoded = base64.b64decode(data["media"]["payload"])
        # 16 kHz → 8 kHz halves the samples; 100 ms @8k = 1600 bytes
        assert len(decoded) == 1600

    def test_media_chunked_100ms(self):
        s = ExotelSerializer(stream_sid="s", exotel_sample_rate=16000)
        msgs = s.media_messages(b"\x00\x00" * 8000, 16000)  # 500 ms
        assert len(msgs) == 5

    def test_same_rate_passthrough(self):
        pcm = b"\x05\x00" * 100
        assert resample_pcm16(pcm, 16000, 16000) == pcm

    def test_resample_halves_length(self):
        pcm = np.zeros(1600, dtype=np.int16).tobytes()
        out = resample_pcm16(pcm, 16000, 8000)
        assert len(np.frombuffer(out, dtype=np.int16)) == 800

    def test_clear_message(self):
        s = ExotelSerializer(stream_sid="sid-9")
        data = json.loads(s.clear_message())
        assert data == {"event": "clear", "stream_sid": "sid-9"}

    def test_mark_message(self):
        s = ExotelSerializer(stream_sid="sid-9")
        data = json.loads(s.mark_message("utterance-3"))
        assert data["event"] == "mark"
        assert data["stream_sid"] == "sid-9"
        assert data["mark"]["name"] == "utterance-3"

    def test_decode_to_internal(self):
        s = ExotelSerializer(exotel_sample_rate=8000)
        pcm = np.arange(800, dtype=np.int16).tobytes()
        out = s.decode_media_to_internal(pcm, 16000)
        assert len(np.frombuffer(out, dtype=np.int16)) == 1600


# ---------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------

class TestExotelTransport:
    def test_receive_events(self):
        ws = FakeWebSocket(['{"event": "connected"}', _start_msg()])
        t = ExotelTransport(ws)
        e1 = asyncio.run(t.receive())
        assert isinstance(e1, ev.ConnectedEvent)
        e2 = asyncio.run(t.receive())
        assert isinstance(e2, ev.StartEvent)
        assert t.serializer.stream_sid == "sid-1"  # bound after start
        assert t.started

    def test_malformed_dropped_next_returned(self):
        ws = FakeWebSocket(["{bad json", '{"event": "clear"}'])
        t = ExotelTransport(ws)
        e = asyncio.run(t.receive())
        assert isinstance(e, ev.ClearEvent)

    def test_oversize_dropped(self):
        ws = FakeWebSocket(["x" * (MAX_MESSAGE_BYTES + 10),
                            '{"event": "stop"}'])
        t = ExotelTransport(ws)
        e = asyncio.run(t.receive())
        assert isinstance(e, ev.StopEvent)

    def test_unknown_event_skipped(self):
        ws = FakeWebSocket(['{"event": "mystery"}', '{"event": "clear"}'])
        t = ExotelTransport(ws)
        e = asyncio.run(t.receive())
        assert isinstance(e, ev.ClearEvent)

    def test_disconnect_raises(self):
        ws = FakeWebSocket([None])
        t = ExotelTransport(ws)
        with pytest.raises(TransportClosed):
            asyncio.run(t.receive())

    def test_send_audio(self):
        ws = FakeWebSocket()
        t = ExotelTransport(ws, exotel_sample_rate=16000)
        t.serializer.stream_sid = "sid-7"
        asyncio.run(t.start())
        asyncio.run(t.send_audio(b"\x00\x00" * 3200, 16000))  # 200 ms
        msgs = ws.sent_events()
        assert all(m["event"] == "media" for m in msgs)
        assert all(m["stream_sid"] == "sid-7" for m in msgs)
        assert len(msgs) == 2  # two 100 ms chunks
        assert t.media_sent == 2

    def test_clear_sends_event(self):
        ws = FakeWebSocket()
        t = ExotelTransport(ws)
        t.serializer.stream_sid = "sid-7"
        asyncio.run(t.start())
        asyncio.run(t.clear_audio())
        assert ws.sent_events()[-1] == {"event": "clear",
                                        "stream_sid": "sid-7"}

    def test_close_idempotent_and_blocks_sends(self):
        ws = FakeWebSocket()
        t = ExotelTransport(ws)
        asyncio.run(t.start())
        asyncio.run(t.close())
        asyncio.run(t.close())  # no-op
        assert ws.closed
        with pytest.raises(TransportClosed):
            asyncio.run(t.send_audio(b"\x00\x00" * 100, 16000))

    def test_send_failure_marks_closed(self):
        class FailingWS(FakeWebSocket):
            async def send_text(self, msg):
                raise RuntimeError("ws blew up")
        t = ExotelTransport(FailingWS())
        asyncio.run(t.start())
        with pytest.raises(TransportClosed):
            asyncio.run(t.send_audio(b"\x00\x00" * 100, 16000))
        assert not t.connected


# ---------------------------------------------------------------------
# Call sessions
# ---------------------------------------------------------------------

class TestCallSession:
    def test_session_isolation(self, monkeypatch, tmp_path):
        async def scenario():
            s1 = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            s2 = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            assert s1.agent.conversation is not s2.agent.conversation
            assert s1.state is not s2.state
            assert s1.turns is not s2.turns
            assert s1.session_id != s2.session_id
        asyncio.run(scenario())

    def test_full_call_flow(self, monkeypatch, tmp_path):
        """Simulated Exotel sequence: connected → start → media → stop."""
        silence = np.zeros(1600, dtype=np.int16).tobytes()  # 100 ms
        inbound = [
            '{"event": "connected"}',
            _start_msg(),
            _media_msg(silence),
            _media_msg(silence),
            '{"event": "dtmf", "dtmf": {"digit": "0"}}',
            '{"event": "stop", "call_sid": "call-1"}',
        ]
        ws = FakeWebSocket(inbound, delay_s=0.05)

        async def scenario():
            session = _make_session(monkeypatch, ws, tmp_path)
            await session.run()
            return session

        session = asyncio.run(scenario())
        # Call identifiers captured
        assert session.call_id == "call-1"
        assert session.stream_id == "sid-1"
        # Greeting went out over the wire as media + a mark
        kinds = [m["event"] for m in ws.sent_events()]
        assert "media" in kinds and "mark" in kinds
        # Media reached STT
        assert len(session.stt.received) == 2
        # Stop finalizes: reason, log saved, everything closed
        assert session.disconnect_reason == "stop_event"
        assert session.stt.stopped
        assert not session.tts.is_open
        assert ws.closed
        log = json.loads(next(tmp_path.glob("call-*.json")).read_text())
        assert log["transport"] == "exotel"
        assert log["disconnect_reason"] == "stop_event"
        assert log["media_events_received"] == 2
        assert DUMMY_KEY not in json.dumps(log)

    def test_disconnect_finalizes(self, monkeypatch, tmp_path):
        ws = FakeWebSocket(['{"event": "connected"}', _start_msg(), None])

        async def scenario():
            session = _make_session(monkeypatch, ws, tmp_path)
            await session.run()
            return session

        session = asyncio.run(scenario())
        assert session.disconnect_reason == "ws_disconnect"
        assert ws.closed

    def test_barge_in_cancels_and_counts(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            await session.transport.start()
            session.state.transition(AgentState.LISTENING)
            session.state.transition(AgentState.PROCESSING)
            session.state.transition(AgentState.SPEAKING)
            session._on_speech_start()   # caller talks over bot audio
            assert session.state.state is AgentState.INTERRUPTED
            assert session.barge_in_count == 1
            await asyncio.sleep(0.1)  # let scheduled clear coroutine run
            # Exotel clear was sent
            kinds = [m["event"] for m in
                     session.transport._ws.sent_events()]
            assert "clear" in kinds
            await session.shutdown()
        asyncio.run(scenario())

    def test_brand_correction_on_finals(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            await session.transport.start()
            await session.stt.start()
            session.state.transition(AgentState.LISTENING)
            session._on_final("Help me with my Jathura account", "en-IN")
            text, lang, _timings = session._turn_queue.get_nowait()
            assert "Zhatura" in text
            assert session.turns[-1]["text"].startswith("Help me")
            await session.shutdown()
        asyncio.run(scenario())

    def test_human_request_flagged_not_transferred(self, monkeypatch,
                                                   tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            await session.transport.start()
            session.state.transition(AgentState.LISTENING)
            session._on_final("I want to talk to a human", "en-IN")
            assert session.human_requested is True
            assert session.state.state is AgentState.LISTENING  # no transfer
            await session.shutdown()
        asyncio.run(scenario())

    def test_end_phrase_closes_call(self, monkeypatch, tmp_path):
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            await session.transport.start()
            await session.tts.open("en-IN")
            session.state.transition(AgentState.LISTENING)
            session.state.transition(AgentState.PROCESSING)
            await session._respond("thank you, that's all", "en-IN",
                                   TurnTimings())
            assert session.disconnect_reason == "user_end_phrase"
            assert session._stop.is_set()
            # closing was spoken to the caller
            assert any("Thank you for contacting Zhatura" in t
                       for t in session.tts.spoken)
            await session.shutdown()
            assert session.transport._ws.closed
        asyncio.run(scenario())

    def test_normal_turn_end_to_end(self, monkeypatch, tmp_path):
        """USER final → LLM reply → TTS → Exotel media + mark + latency."""
        async def scenario():
            session = _make_session(monkeypatch, FakeWebSocket(), tmp_path)
            await session.transport.start()
            await session.tts.open("en-IN")
            session.state.transition(AgentState.LISTENING)
            timings = TurnTimings()
            timings.speech_end = 1.0
            timings.final_transcript = 1.2
            session.state.transition(AgentState.PROCESSING)
            await session._respond("My lesson is missing", "en-IN",
                                   timings)
            assert session.turn_count == 1
            kinds = [m["event"] for m in
                     session.transport._ws.sent_events()]
            assert "media" in kinds and "mark" in kinds
            assert session.tts.spoken == ["I can help with that."]
            assert session.latencies[-1]["llm_ms"] is not None
            # LLM got a Tamil-style language hint? here English
            messages = (session.stt._client.chat.completions
                        .call_args.kwargs["messages"])
            assert any(m["role"] == "system" and "English" in m["content"]
                       for m in messages[1:])
            await session.shutdown()
        asyncio.run(scenario())

    def test_no_caller_number_stored(self, monkeypatch, tmp_path):
        """Custom params (may contain numbers) never reach the call log."""
        start = json.dumps({"event": "start", "start": {
            "stream_sid": "s-priv", "call_sid": "c-priv",
            "custom_parameters": {"caller": "+919000001111"}}})
        ws = FakeWebSocket([start, '{"event": "stop"}'], delay_s=0.05)

        async def scenario():
            session = _make_session(monkeypatch, ws, tmp_path)
            await session.run()
            return session

        asyncio.run(scenario())
        log_text = next(tmp_path.glob("call-*.json")).read_text()
        assert "+919000001111" not in log_text  # caller number not stored
        assert DUMMY_KEY not in log_text

    def test_concurrent_sessions(self, monkeypatch, tmp_path):
        """Two simulated calls at once stay independent (§61)."""
        inbound_a = ['{"event": "connected"}', _start_msg("sa", "ca"),
                     '{"event": "stop", "call_sid": "ca"}']
        inbound_b = ['{"event": "connected"}', _start_msg("sb", "cb"),
                     '{"event": "stop", "call_sid": "cb"}']

        async def scenario():
            sa = _make_session(monkeypatch, FakeWebSocket(inbound_a),
                               tmp_path)
            sb = _make_session(monkeypatch, FakeWebSocket(inbound_b),
                               tmp_path)
            await asyncio.gather(sa.run(), sb.run())
            return sa, sb

        sa, sb = asyncio.run(scenario())
        assert sa.call_id == "ca" and sb.call_id == "cb"
        assert sa.stream_id == "sa" and sb.stream_id == "sb"
        assert sa.disconnect_reason == "stop_event"
        assert sb.disconnect_reason == "stop_event"
        logs = sorted(p.read_text() for p in tmp_path.glob("call-*.json"))
        assert len(logs) == 2
