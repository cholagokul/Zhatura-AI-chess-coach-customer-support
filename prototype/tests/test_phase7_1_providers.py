"""Zhatura AI Customer Care — Phase 7.1 Automated Provider Failover Tests.

Tests dual-provider resilience (Sarvam + ElevenLabs):
- Provider health tracking, circuit breaker, and cooldown
- Initial provider selection (primary vs fallback)
- In-call failover on STT failure
- In-call failover on TTS failure
- Provider lock and no ping-pong (max 1 failover per call)
- Discarding stale audio / transcripts via generation counters
- Preservation of conversation turns, caller language, and Phase 7 tool states
- Dual-provider outage -> static emergency audio & clean hangup
- FastAPI health endpoint diagnostics
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest import mock
import pytest
from fastapi.testclient import TestClient

import config
from agent.conversation import Conversation
from agent.languages import normalize_language_code
from agent.state import AgentState
from agent.voice_agent import VoiceAgent
from phase4_exotel_server import create_app
from speech.providers import (
    AllProvidersUnavailableError,
    ElevenLabsProvider,
    FailoverLimitExceededError,
    ProviderAuthError,
    ProviderHealthManager,
    ProviderQuotaExhaustedError,
    ProviderUnavailableError,
    SarvamProvider,
    VoiceProviderManager,
    get_emergency_audio_pcm,
)
from speech.providers.emergency_audio import generate_emergency_pcm
from telephony.session import CallSession, TelephonyAudioSink
from transports.exotel import ExotelTransport


class FakeWebSocket:
    """In-memory stand-in for Starlette / Exotel WebSocket."""

    def __init__(self, inbound=(), delay_s: float = 0.0):
        self._in: asyncio.Queue = asyncio.Queue()
        for m in inbound:
            self._in.put_nowait(m)
        self.sent: list[str] = []
        self.closed = False
        self._delay = delay_s

    async def receive_text(self):
        if self._delay:
            await asyncio.sleep(self._delay)
        msg = await self._in.get()
        if msg is None:
            raise RuntimeError("WebSocket disconnected")
        return msg

    async def send_text(self, msg: str):
        self.sent.append(msg)
        try:
            data = json.loads(msg)
        except ValueError:
            return
        if data.get("event") == "mark":
            # Echo mark back like Exotel
            self._in.put_nowait(
                json.dumps({"event": "mark", "mark": {"name": data["mark"]["name"]}})
            )

    async def close(self):
        self.closed = True
        self._in.put_nowait(None)

    def sent_events(self):
        return [json.loads(m) for m in self.sent]


class FakeScriptedProvider:
    """Mock VoiceProvider for deterministic failover scenario testing."""

    def __init__(self, name: str, fail_on_stt: bool = False, fail_on_tts: bool = False):
        self._name = name
        self.fail_on_stt = fail_on_stt
        self.fail_on_tts = fail_on_tts
        self.started = False
        self.stopped = False
        self.sent_audio_chunks: list[bytes] = []
        self.synthesized_texts: list[str] = []

        self.on_speech_start = lambda: None
        self.on_speech_end = lambda: None
        self.on_partial = lambda _t: None
        self.on_final = lambda _t, _l: None
        self.on_error = lambda _m: None

        # Duck-type stt and tts properties for CallSession back-compat
        self.stt = mock.Mock()
        self.stt.on_speech_start = lambda: None
        self.stt.on_speech_end = lambda: None
        self.stt.on_final = lambda _t, _l: None
        self.stt.on_error = lambda _m: None
        self.stt.send_audio = self.send_audio
        self.tts = mock.Mock()
        self.tts.is_open = False
        self.tts.synthesize = self.synthesize

    @property
    def name(self) -> str:
        return self._name

    async def start(self, tts_language: str = "en-IN") -> None:
        self.started = True
        self.tts.is_open = True

    async def stop(self) -> None:
        self.stopped = True
        self.tts.is_open = False

    def wire_stt_callbacks(self, **kwargs) -> None:
        if kwargs.get("on_speech_start"):
            self.on_speech_start = kwargs["on_speech_start"]
        if kwargs.get("on_speech_end"):
            self.on_speech_end = kwargs["on_speech_end"]
        if kwargs.get("on_partial"):
            self.on_partial = kwargs["on_partial"]
        if kwargs.get("on_final"):
            self.on_final = kwargs["on_final"]
        if kwargs.get("on_error"):
            self.on_error = kwargs["on_error"]

    async def send_audio(self, pcm_bytes: bytes) -> None:
        if self.fail_on_stt:
            raise ProviderUnavailableError(f"{self._name} STT simulated crash", provider=self._name)
        self.sent_audio_chunks.append(pcm_bytes)

    async def synthesize(self, text: str, language_code: str, on_audio_chunk) -> None:
        if self.fail_on_tts:
            raise ProviderQuotaExhaustedError(f"{self._name} TTS simulated quota exhaustion", provider=self._name)
        self.synthesized_texts.append(text)
        await on_audio_chunk(b"fake-mp3-chunk")

    def supports_tts_language(self, language_code: str) -> bool:
        return True

    def supports_stt_language(self, language_code: str) -> bool:
        return True

    def map_tts_language(self, language_code: str, fallback: str = "en-IN") -> str:
        return language_code


def _make_test_cfg(**overrides):
    base = config.load_config()
    data = base.__dict__.copy()
    if "elevenlabs_api_key" not in overrides and not data.get("elevenlabs_api_key"):
        data["elevenlabs_api_key"] = "test-eleven-key"
    data.update(overrides)
    return config.Config(**data)


# =====================================================================
# 1. Health Manager & Circuit Breaker Tests
# =====================================================================

class TestProviderHealthManager:
    def test_initial_state_healthy(self):
        hm = ProviderHealthManager()
        assert hm.is_healthy("sarvam") is True
        assert hm.is_healthy("elevenlabs") is True

    def test_circuit_breaker_trip(self):
        hm = ProviderHealthManager(default_cooldown_seconds=100.0)
        hm.record_failure("sarvam", "Quota exhausted 402", hard_break=True)
        assert hm.is_healthy("sarvam") is False
        assert hm.is_healthy("elevenlabs") is True

        rep = hm.get_status_report()
        assert rep["sarvam"]["status"] == "unhealthy"
        assert rep["sarvam"]["circuit_open"] is True
        assert rep["sarvam"]["failure_count"] == 1
        assert "402" in rep["sarvam"]["last_failure_reason"]
        assert rep["sarvam"]["cooldown_remaining_seconds"] > 0

    def test_cooldown_expiration(self):
        hm = ProviderHealthManager(default_cooldown_seconds=0.1)
        hm.record_failure("sarvam", "Temporary network drop", cooldown_seconds=0.05)
        assert hm.is_healthy("sarvam") is False

        # Wait for cooldown to expire
        time.sleep(0.08)
        assert hm.is_healthy("sarvam") is True

        # Successful call resets circuit
        hm.record_success("sarvam")
        rep = hm.get_status_report()
        assert rep["sarvam"]["status"] == "healthy"
        assert rep["sarvam"]["circuit_open"] is False

    def test_reset_functionality(self):
        hm = ProviderHealthManager()
        hm.record_failure("elevenlabs", "Simulated timeout")
        assert hm.is_healthy("elevenlabs") is False
        hm.reset("elevenlabs")
        assert hm.is_healthy("elevenlabs") is True


# =====================================================================
# 2. Voice Provider Manager Tests
# =====================================================================

class TestVoiceProviderManager:
    def test_select_primary_when_healthy(self):
        cfg = _make_test_cfg(voice_primary_provider="sarvam", voice_secondary_provider="elevenlabs")
        mgr = VoiceProviderManager(cfg=cfg)
        provider, name = mgr.select_initial_provider()
        assert name == "sarvam"
        assert isinstance(provider, SarvamProvider)

    def test_select_secondary_when_primary_unhealthy(self):
        cfg = _make_test_cfg(voice_primary_provider="sarvam", voice_secondary_provider="elevenlabs")
        mgr = VoiceProviderManager(cfg=cfg)
        mgr.record_failure("sarvam", "Down")
        provider, name = mgr.select_initial_provider()
        assert name == "elevenlabs"
        assert isinstance(provider, ElevenLabsProvider)

    def test_raises_when_all_unhealthy(self):
        cfg = _make_test_cfg(voice_primary_provider="sarvam", voice_secondary_provider="elevenlabs")
        mgr = VoiceProviderManager(cfg=cfg)
        mgr.record_failure("sarvam", "Down")
        mgr.record_failure("elevenlabs", "Down")
        with pytest.raises(AllProvidersUnavailableError):
            mgr.select_initial_provider()

    def test_get_failover_candidate_and_limit(self):
        cfg = _make_test_cfg(voice_primary_provider="sarvam", voice_secondary_provider="elevenlabs", max_provider_failovers_per_call=1)
        mgr = VoiceProviderManager(cfg=cfg)
        new_provider, new_name = mgr.get_failover_candidate("sarvam", failover_count=0)
        assert new_name == "elevenlabs"

        # Max 1 failover reached: second failover attempt disallowed
        with pytest.raises(FailoverLimitExceededError):
            mgr.get_failover_candidate("elevenlabs", failover_count=1)


# =====================================================================
# 3. Provider Interface & Simulation Tests
# =====================================================================

class TestProviderImplementations:
    def test_sarvam_provider_languages(self):
        cfg = _make_test_cfg()
        p = SarvamProvider(cfg=cfg)
        assert p.supports_tts_language("en-IN") is True
        assert p.supports_tts_language("hi-IN") is True
        assert p.supports_tts_language("ur-IN") is False  # Urdu not in Bulbul v3
        assert p.map_tts_language("ur-IN", fallback="en-IN") == "en-IN"

    def test_elevenlabs_provider_languages(self):
        cfg = _make_test_cfg()
        p = ElevenLabsProvider(cfg=cfg)
        # ElevenLabs multilingual supports English, Hindi, Tamil, etc.
        assert p.supports_tts_language("en-IN") is True
        assert p.supports_tts_language("hi-IN") is True
        assert p.supports_tts_language("ta-IN") is True
        assert p.supports_tts_language("ur-IN") is True

    def test_sarvam_simulated_failures(self):
        cfg = _make_test_cfg(sarvam_fail_mode="quota")
        p = SarvamProvider(cfg=cfg)
        with pytest.raises(ProviderQuotaExhaustedError):
            asyncio.run(p.start())

    def test_elevenlabs_simulated_failures(self):
        cfg = _make_test_cfg(elevenlabs_fail_mode="auth")
        p = ElevenLabsProvider(cfg=cfg)
        with pytest.raises(ProviderAuthError):
            asyncio.run(p.send_audio(b"\x00" * 320))


# =====================================================================
# 4. Static Emergency Audio Tests
# =====================================================================

class TestStaticEmergencyAudio:
    def test_emergency_pcm_format(self):
        pcm = get_emergency_audio_pcm()
        assert isinstance(pcm, bytes)
        assert len(pcm) > 0
        # Must be 16-bit PCM (2 bytes per sample)
        assert len(pcm) % 2 == 0
        # Must be multiple of 100ms frames (16000 * 2 * 0.1 = 3200 bytes)
        # Or at least 1 second of audio
        assert len(pcm) >= 16000 * 2

    def test_custom_duration_pcm(self):
        pcm = generate_emergency_pcm(duration_seconds=1.0)
        assert len(pcm) == int(16000 * 1.0 * 2)


# =====================================================================
# 5. In-Call Dual Provider Failover Integration Tests
# =====================================================================

class TestCallSessionDualProviderFailover:
    def _create_test_session(self, primary_provider, secondary_provider, cfg=None):
        if cfg is None:
            cfg = _make_test_cfg()
        ws = FakeWebSocket()
        transport = ExotelTransport(ws)
        transport.serializer.stream_sid = "sid-test-1"

        mgr = VoiceProviderManager(cfg=cfg)
        # Patch create_provider to return our scripted fakes
        def mock_create(name, **kwargs):
            if name == "sarvam":
                return primary_provider
            elif name == "elevenlabs":
                return secondary_provider
            raise ValueError(name)

        mgr.create_provider = mock_create
        session = CallSession(cfg, transport, provider_manager=mgr)
        session.sink.finish = lambda: None
        return session, transport, ws

    def test_call_starts_on_locked_primary(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam")
            p2 = FakeScriptedProvider("elevenlabs")
            session, _, _ = self._create_test_session(p1, p2)

            assert session.active_voice_provider == "sarvam"
            assert session.initial_voice_provider == "sarvam"
            assert session.failover_occurred is False
            assert session.failover_count == 0
            assert session.provider_generation == 0

        asyncio.run(scenario())

    def test_stt_failure_triggers_atomic_failover(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam", fail_on_stt=True)
            p2 = FakeScriptedProvider("elevenlabs")
            session, transport, _ = self._create_test_session(p1, p2)
            await transport.start()
            await session._provider.start()
            session._wire_provider_stt(session._provider, session.provider_generation)

            # Simulate incoming media event
            from telephony.exotel_events import MediaEvent
            event = MediaEvent(payload=b"\x00\x00" * 160, sequence="1", timestamp="100")
            await session._handle_event(event)

            return session, p1, p2

        session, p1, p2 = asyncio.run(scenario())
        # Failover occurred: Sarvam -> ElevenLabs
        assert session.failover_occurred is True
        assert session.failover_count == 1
        assert session.active_voice_provider == "elevenlabs"
        assert session.initial_voice_provider == "sarvam"
        assert session.provider_generation == 1
        assert p1.stopped is True
        assert p2.started is True
        assert "stt" in session.failover_reason.lower()

    def test_tts_failure_triggers_atomic_failover(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam", fail_on_tts=True)
            p2 = FakeScriptedProvider("elevenlabs")
            session, transport, _ = self._create_test_session(p1, p2)
            await transport.start()

            # Attempt reply synthesis which fails on p1
            timings = mock.Mock()
            timings.speech_end = time.monotonic()
            timings.stt_final_ms.return_value = 100
            timings.llm_ms.return_value = 150
            timings.tts_first_audio_ms.return_value = 200
            timings.total_ms.return_value = 450

            session.agent.generate_reply = mock.AsyncMock(return_value="Helpful response")
            await session._respond("I need help with login", "en-IN", timings)
            return session, p1, p2

        session, p1, p2 = asyncio.run(scenario())
        assert session.failover_occurred is True
        assert session.active_voice_provider == "elevenlabs"
        assert p2.synthesized_texts == ["Helpful response"]
        assert session.failover_count == 1

    def test_failover_lock_prevents_ping_pong(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam", fail_on_tts=True)
            p2 = FakeScriptedProvider("elevenlabs", fail_on_tts=True)
            session, transport, ws = self._create_test_session(p1, p2)
            await transport.start()

            # First failure -> failover to elevenlabs (failover_count becomes 1)
            ok1 = await session.failover_provider("sarvam failed")
            assert ok1 is True
            assert session.active_voice_provider == "elevenlabs"
            assert session.failover_count == 1

            # Second failure -> attempt failover back to sarvam is DENIED
            ok2 = await session.failover_provider("elevenlabs also failed")
            assert ok2 is False
            # Session initiated clean emergency shutdown
            assert session.disconnect_reason == "dual_provider_failure"
            return session, ws

        session, ws = asyncio.run(scenario())
        assert session.failover_count == 1

    def test_stale_event_rejected_by_generation_counter(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam")
            p2 = FakeScriptedProvider("elevenlabs")
            session, _, _ = self._create_test_session(p1, p2)

            turns_before = len(session.turns)

            # Wire callbacks for generation 0
            session._wire_provider_stt(p1, generation=0)

            # Simulate failover: generation increments to 1
            session.provider_generation = 1

            # Late transcript arrives from generation 0
            p1.on_final("stale message from old provider", "en-IN")

            # Must be rejected; turns count unchanged
            assert len(session.turns) == turns_before

        asyncio.run(scenario())

    def test_state_and_language_preserved_across_failover(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam", fail_on_tts=True)
            p2 = FakeScriptedProvider("elevenlabs")
            session, transport, _ = self._create_test_session(p1, p2)
            await transport.start()

            # Set caller language and conversation history before failover
            session.requested_language = "ta-IN"
            session.reply_language = "ta-IN"
            session.agent.conversation.add_user("வணக்கம், எனது கணக்கு நிலுவை என்ன?")
            session.agent.conversation.add_assistant("வணக்கம்! சரிபார்க்கிறேன்.")
            session.turns.append({"speaker": "user", "text": "வணக்கம்", "language": "ta-IN"})

            # Trigger failover
            await session.failover_provider("TTS failed on Sarvam")

            return session

        session = asyncio.run(scenario())
        # Language, conversation, turns all preserved!
        assert session.reply_language == "ta-IN"
        assert session.requested_language == "ta-IN"
        assert len(session.agent.conversation.messages()) == 3
        assert len(session.turns) == 1

    def test_both_providers_fail_plays_emergency_audio(self):
        async def scenario():
            p1 = FakeScriptedProvider("sarvam", fail_on_tts=True)
            p2 = FakeScriptedProvider("elevenlabs", fail_on_tts=True)
            session, transport, ws = self._create_test_session(p1, p2)
            await transport.start()

            # Trigger dual provider failure
            session.failover_count = 1  # Already failed over once
            await session.failover_provider("Second provider failed")
            return session, ws

        session, ws = asyncio.run(scenario())
        assert session.disconnect_reason == "dual_provider_failure"
        sent = ws.sent_events()
        # Exotel media events were sent with emergency audio
        media_events = [m for m in sent if m.get("event") == "media"]
        assert len(media_events) > 0


# =====================================================================
# 6. Server Health Endpoint Tests
# =====================================================================

class TestPhase7_1HealthEndpoint:
    def test_health_endpoint_contract(self):
        cfg = _make_test_cfg(
            voice_primary_provider="sarvam",
            voice_secondary_provider="elevenlabs",
            support_backend_mode="mock",
        )
        app = create_app(cfg)
        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "healthy"
        assert data["sarvam"] == "configured"
        assert data["phase"] == 7
        assert data["phase_version"] == "7.1"
        assert data["voice_primary_provider"] == "sarvam"
        assert data["voice_secondary_provider"] == "elevenlabs"
        assert "sarvam" in data["providers"]
        assert "elevenlabs" in data["providers"]
        assert data["providers"]["sarvam"]["status"] == "healthy"
        assert data["providers"]["elevenlabs"]["status"] == "healthy"
