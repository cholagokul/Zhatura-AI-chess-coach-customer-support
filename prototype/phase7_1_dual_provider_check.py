"""Zhatura AI Customer Care — Phase 7.1 Dual Voice Provider Verification Script.

Executes and verifies Scenarios A through J for dual-provider failover
(Sarvam + ElevenLabs) with zero live costs/credits needed.
Run with:
    python prototype/phase7_1_dual_provider_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest import mock

# Ensure prototype is on sys.path
PROTOTYPE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROTOTYPE_DIR))

import config
from agent.conversation import Conversation
from agent.voice_agent import VoiceAgent
from speech.providers import (
    AllProvidersUnavailableError,
    ElevenLabsProvider,
    FailoverLimitExceededError,
    ProviderHealthManager,
    SarvamProvider,
    VoiceProvider,
    VoiceProviderManager,
    get_emergency_audio_pcm,
)
from telephony.exotel_events import MediaEvent
from telephony.session import CallSession
from tools import CallerIdentity, CallerRole, SupportToolService
from transports.exotel import ExotelTransport


class ScriptedWebSocket:
    """Mock WebSocket for end-to-end simulation."""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def receive_text(self):
        await asyncio.sleep(0.01)
        return json.dumps({"event": "media", "media": {"payload": "AAAA", "chunk": "1"}})

    async def send_text(self, msg: str):
        try:
            self.sent.append(json.loads(msg))
        except Exception:
            pass

    async def close(self):
        self.closed = True


class ScriptedVoiceProvider(VoiceProvider):
    """Controllable voice provider for simulation scenarios."""

    def __init__(self, name: str, fail_stt: bool = False, fail_tts: bool = False):
        self._name = name
        self.fail_stt = fail_stt
        self.fail_tts = fail_tts
        self.is_started = False
        self.is_stopped = False
        self.audio_sent: list[bytes] = []
        self.synthesized: list[str] = []

        self.on_speech_start = lambda: None
        self.on_speech_end = lambda: None
        self.on_partial = lambda _t: None
        self.on_final = lambda _t, _l: None
        self.on_error = lambda _m: None

        self._stt = mock.Mock()
        self._stt.on_speech_start = lambda: None
        self._stt.on_speech_end = lambda: None
        self._stt.on_final = lambda _t, _l: None
        self._stt.on_error = lambda _m: None
        self._stt.send_audio = self.send_audio
        self._tts = mock.Mock()
        self._tts.is_open = False
        self._tts.synthesize = self.synthesize

    @property
    def name(self) -> str:
        return self._name

    @property
    def stt(self):
        return self._stt

    @property
    def tts(self):
        return self._tts

    async def start(self, tts_language: str = "en-IN") -> None:
        self.is_started = True
        self.tts.is_open = True

    async def stop(self) -> None:
        self.is_stopped = True
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
        if self.fail_stt:
            raise RuntimeError(f"{self._name} STT connection dropped")
        self.audio_sent.append(pcm_bytes)

    async def synthesize(self, text: str, language_code: str, on_audio_chunk) -> None:
        if self.fail_tts:
            raise RuntimeError(f"{self._name} TTS quota limit reached")
        self.synthesized.append(text)
        await on_audio_chunk(b"chunk")

    def supports_tts_language(self, language_code: str) -> bool:
        return True

    def supports_stt_language(self, language_code: str) -> bool:
        return True

    def map_tts_language(self, language_code: str, fallback: str = "en-IN") -> str:
        return language_code


def _build_test_session(primary, secondary, cfg_overrides=None):
    base_cfg = config.load_config()
    cfg_dict = base_cfg.__dict__.copy()
    if cfg_overrides:
        cfg_dict.update(cfg_overrides)
    cfg = config.Config(**cfg_dict)

    ws = ScriptedWebSocket()
    transport = ExotelTransport(ws)
    transport.serializer.stream_sid = "sim-sid-1"

    mgr = VoiceProviderManager(cfg=cfg)
    mgr.create_provider = lambda name, **kw: primary if name == primary.name else secondary
    session = CallSession(cfg, transport, provider_manager=mgr)
    session.sink.finish = lambda: None
    return session, transport, ws


async def run_scenario_a():
    """Scenario A: Clean call with primary provider (Sarvam)."""
    p1 = ScriptedVoiceProvider("sarvam")
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, transport, _ = _build_test_session(p1, p2)

    await session._provider.start()
    session._wire_provider_stt(session._provider, session.provider_generation)

    # Ingest user audio and synthesize reply
    await session._handle_event(MediaEvent(payload=b"\x00" * 320, sequence="1"))
    timings = mock.Mock()
    timings.speech_end = time.monotonic()
    timings.stt_final_ms.return_value = 120
    timings.llm_ms.return_value = 180
    timings.tts_first_audio_ms.return_value = 210
    timings.total_ms.return_value = 510

    session.agent.generate_reply = mock.AsyncMock(return_value="Welcome to Zhatura!")
    await session._respond("Hello", "en-IN", timings)

    assert session.active_voice_provider == "sarvam"
    assert session.failover_occurred is False
    assert session.failover_count == 0
    assert p1.synthesized == ["Welcome to Zhatura!"]
    assert len(p2.synthesized) == 0
    return True


async def run_scenario_b():
    """Scenario B: Mid-call STT failure triggers failover to ElevenLabs."""
    p1 = ScriptedVoiceProvider("sarvam", fail_stt=True)
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, transport, _ = _build_test_session(p1, p2)

    await session._provider.start()
    session._wire_provider_stt(session._provider, session.provider_generation)

    # Ingest audio -> STT failure triggers failover
    await session._handle_event(MediaEvent(payload=b"\x00" * 320, sequence="1"))

    assert session.failover_occurred is True
    assert session.failover_count == 1
    assert session.active_voice_provider == "elevenlabs"
    assert p1.is_stopped is True
    assert p2.is_started is True
    assert "stt" in session.failover_reason.lower()
    return True


async def run_scenario_c():
    """Scenario C: Mid-call TTS failure triggers failover to ElevenLabs."""
    p1 = ScriptedVoiceProvider("sarvam", fail_tts=True)
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, transport, _ = _build_test_session(p1, p2)

    await session._provider.start()
    session._wire_provider_stt(session._provider, session.provider_generation)

    timings = mock.Mock()
    timings.speech_end = time.monotonic()
    timings.stt_final_ms.return_value = 100
    timings.llm_ms.return_value = 100
    timings.tts_first_audio_ms.return_value = 100
    timings.total_ms.return_value = 300

    session.agent.generate_reply = mock.AsyncMock(return_value="Failover reply")
    await session._respond("Need help", "en-IN", timings)

    assert session.failover_occurred is True
    assert session.failover_count == 1
    assert session.active_voice_provider == "elevenlabs"
    assert p2.synthesized == ["Failover reply"]
    return True


async def run_scenario_d():
    """Scenario D: Call start when primary is unhealthy (starts on ElevenLabs)."""
    p1 = ScriptedVoiceProvider("sarvam")
    p2 = ScriptedVoiceProvider("elevenlabs")

    base_cfg = config.load_config()
    cfg_dict = base_cfg.__dict__.copy()
    cfg = config.Config(**cfg_dict)

    ws = ScriptedWebSocket()
    transport = ExotelTransport(ws)
    transport.serializer.stream_sid = "sim-sid-d"

    mgr = VoiceProviderManager(cfg=cfg)
    mgr.create_provider = lambda name, **kw: p1 if name == "sarvam" else p2
    # Sarvam marked unhealthy
    mgr.record_failure("sarvam", "Previous call outage")

    session = CallSession(cfg, transport, provider_manager=mgr)
    session.sink.finish = lambda: None

    assert session.active_voice_provider == "elevenlabs"
    assert session.initial_voice_provider == "elevenlabs"
    assert session.failover_occurred is False
    assert session.failover_count == 0
    return True


async def run_scenario_e():
    """Scenario E: Reverse failover when ElevenLabs is primary and experiences failure."""
    p1 = ScriptedVoiceProvider("elevenlabs", fail_tts=True)
    p2 = ScriptedVoiceProvider("sarvam")
    session, transport, _ = _build_test_session(
        p1, p2, cfg_overrides={"voice_primary_provider": "elevenlabs", "voice_secondary_provider": "sarvam"}
    )

    await session._provider.start()
    session._wire_provider_stt(session._provider, session.provider_generation)

    timings = mock.Mock()
    timings.speech_end = time.monotonic()
    timings.stt_final_ms.return_value = 100
    timings.llm_ms.return_value = 100
    timings.tts_first_audio_ms.return_value = 100
    timings.total_ms.return_value = 300

    session.agent.generate_reply = mock.AsyncMock(return_value="Reverse failover reply")
    await session._respond("Need help", "en-IN", timings)

    assert session.failover_occurred is True
    assert session.active_voice_provider == "sarvam"
    assert session.initial_voice_provider == "elevenlabs"
    assert p2.synthesized == ["Reverse failover reply"]
    return True


async def run_scenario_f():
    """Scenario F: Failover lock prevents ping-pong when secondary experiences issue."""
    p1 = ScriptedVoiceProvider("sarvam", fail_tts=True)
    p2 = ScriptedVoiceProvider("elevenlabs", fail_tts=True)
    session, transport, _ = _build_test_session(p1, p2)

    # First failover
    ok1 = await session.failover_provider("sarvam crashed")
    assert ok1 is True
    assert session.active_voice_provider == "elevenlabs"
    assert session.failover_count == 1

    # Second failover is blocked
    ok2 = await session.failover_provider("elevenlabs crashed")
    assert ok2 is False
    assert session.failover_count == 1
    assert session.disconnect_reason == "dual_provider_failure"
    return True


async def run_scenario_g():
    """Scenario G: Both providers fail -> static emergency audio and clean hangup."""
    p1 = ScriptedVoiceProvider("sarvam")
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, transport, ws = _build_test_session(p1, p2)
    await transport.start()

    session.failover_count = 1
    await session.failover_provider("Total failure")

    assert session.disconnect_reason == "dual_provider_failure"
    events = ws.sent
    media_events = [e for e in events if e.get("event") == "media"]
    assert len(media_events) > 0
    return True


async def run_scenario_h():
    """Scenario H: Circuit breaker cooldown expiration / recovery test."""
    hm = ProviderHealthManager(default_cooldown_seconds=0.1)
    hm.record_failure("sarvam", "Network blip", cooldown_seconds=0.05)
    assert hm.is_healthy("sarvam") is False

    await asyncio.sleep(0.08)
    # Cooldown passed -> provider is available
    assert hm.is_healthy("sarvam") is True
    hm.record_success("sarvam")
    assert hm.get_status_report()["sarvam"]["status"] == "healthy"
    return True


async def run_scenario_i():
    """Scenario I: Stale event / race condition rejection test."""
    p1 = ScriptedVoiceProvider("sarvam")
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, _, _ = _build_test_session(p1, p2)

    # Initial wiring (gen 0)
    session._wire_provider_stt(p1, 0)
    # Simulate mid-flight failover (gen 1)
    session.provider_generation = 1

    turns_count = len(session.turns)
    # In-flight transcript from gen 0 arrives late
    p1.on_final("Stale transcript from failed provider", "en-IN")

    assert len(session.turns) == turns_count
    return True


async def run_scenario_j():
    """Scenario J: Full conversation state and ticket verification preservation across failover."""
    p1 = ScriptedVoiceProvider("sarvam", fail_tts=True)
    p2 = ScriptedVoiceProvider("elevenlabs")
    session, transport, _ = _build_test_session(p1, p2)

    # Authenticate caller via Phase 7 SupportToolService
    tool_service = SupportToolService(backend_mode="mock")
    await tool_service.verify_caller("ACC-P100")
    assert tool_service.caller.is_verified is True

    session.agent.tool_service = tool_service
    session.requested_language = "hi-IN"
    session.reply_language = "hi-IN"
    session.agent.conversation.add_user("मुझे अपने बच्चे की क्लास का समय जानना है")
    session.agent.conversation.add_assistant("जी हाँ, मैं अभी देख कर बताता हूँ।")

    # Mid-call failover
    await session.failover_provider("TTS failed on Sarvam")

    # All state perfectly preserved
    assert session.agent.tool_service.caller.is_verified is True
    assert session.reply_language == "hi-IN"
    assert session.requested_language == "hi-IN"
    assert len(session.agent.conversation.messages()) == 3
    assert session.active_voice_provider == "elevenlabs"
    return True


async def main():
    print("==================================================")
    print("ZHATURA AI — PHASE 7.1 DUAL VOICE PROVIDER CHECK")
    print("==================================================\n")

    scenarios = [
        ("Scenario A: Clean call on primary provider (Sarvam)", run_scenario_a),
        ("Scenario B: Mid-call STT failure -> ElevenLabs failover", run_scenario_b),
        ("Scenario C: Mid-call TTS failure -> ElevenLabs failover", run_scenario_c),
        ("Scenario D: Call start when primary is unhealthy", run_scenario_d),
        ("Scenario E: Reverse failover (ElevenLabs -> Sarvam)", run_scenario_e),
        ("Scenario F: Failover lock prevents ping-ponging", run_scenario_f),
        ("Scenario G: Dual-provider outage -> Emergency audio", run_scenario_g),
        ("Scenario H: Circuit breaker cooldown expiration", run_scenario_h),
        ("Scenario I: Stale event / race condition rejection", run_scenario_i),
        ("Scenario J: Phase 7 Tool & Language state preservation", run_scenario_j),
    ]

    all_passed = True
    for title, func in scenarios:
        try:
            passed = await func()
            if passed:
                print(f"  [PASS] {title}")
            else:
                print(f"  [FAIL] {title}")
                all_passed = False
        except Exception as exc:
            print(f"  [FAIL] {title} — Error: {exc}")
            all_passed = False

    print("\n==================================================")
    if all_passed:
        print("RESULT: ALL SCENARIOS PASSED (10/10)")
    else:
        print("RESULT: ONE OR MORE SCENARIOS FAILED")
    print("==================================================")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
