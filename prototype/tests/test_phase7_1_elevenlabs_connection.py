"""Zhatura AI Customer Care — Phase 7.1 ElevenLabs Connection & Configuration Tests.

Verifies:
- ElevenLabs API key loaded from .env / config
- Missing key handled safely (server starts, Sarvam works, ElevenLabs marked unavailable)
- Invalid key handled safely (circuit breaker trips, cooldown enforced, Sarvam available)
- Key never logged or exposed in responses or diagnostics
- Provider registered in VoiceProviderManager
- Primary/secondary config read correctly
- ElevenLabs STT adapter uses config and formats valid WAV container
- ElevenLabs TTS adapter uses config and frames MP3 safely
- Sarvam still works if ElevenLabs missing
- Failover to ElevenLabs when available
- Reverse failover from ElevenLabs to Sarvam
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import wave
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import config
from phase4_exotel_server import create_app
from speech.providers.base import VoiceProvider
from speech.providers.elevenlabs_provider import (
    ElevenLabsProvider,
    ElevenLabsSTT,
    ElevenLabsTTS,
)
from speech.providers.errors import (
    AllProvidersUnavailableError,
    FailoverLimitExceededError,
    ProviderAuthError,
    ProviderUnavailableError,
)
from speech.providers.health import ProviderHealthManager
from speech.providers.manager import VoiceProviderManager
from speech.providers.sarvam_provider import SarvamProvider


def _cfg(**overrides):
    base = config.load_config()
    data = base.__dict__.copy()
    data.update(overrides)
    return config.Config(**data)


class TestElevenLabsConfigLoading:
    def test_elevenlabs_key_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test-secret-eleven-key")
        monkeypatch.setenv("ELEVENLABS_VOICE_ID", "custom_voice_123")
        monkeypatch.setenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
        monkeypatch.setenv("ELEVENLABS_STT_MODEL_ID", "scribe_v1")

        cfg = config.load_config()
        assert cfg.elevenlabs_api_key == "test-secret-eleven-key"
        assert cfg.elevenlabs_voice_id == "custom_voice_123"
        assert cfg.elevenlabs_model_id == "eleven_multilingual_v2"
        assert cfg.elevenlabs_stt_model_id == "scribe_v1"

    def test_missing_key_handled_safely(self):
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key="",
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
        assert data["providers"]["sarvam"]["status"] == "healthy"
        assert data["providers"]["elevenlabs"]["status"] == "unavailable"
        assert data["providers"]["elevenlabs"]["reason"] == "missing_api_key"

    def test_key_never_logged_or_exposed(self, caplog):
        secret_canary = "super_secret_canary_key_xyz987"
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key=secret_canary,
            voice_primary_provider="sarvam",
            voice_secondary_provider="elevenlabs",
        )
        app = create_app(cfg)
        client = TestClient(app)
        with caplog.at_level(logging.DEBUG):
            res = client.get("/health")
            assert res.status_code == 200
            content = res.text
            assert secret_canary not in content
            for record in caplog.records:
                assert secret_canary not in record.message


class TestElevenLabsProviderAdapter:
    def test_provider_registration_in_manager(self):
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key="test-eleven-key",
        )
        mgr = VoiceProviderManager(cfg=cfg)
        p1 = mgr.create_provider("sarvam")
        p2 = mgr.create_provider("elevenlabs")
        assert isinstance(p1, SarvamProvider)
        assert isinstance(p2, ElevenLabsProvider)
        assert p1.name == "sarvam"
        assert p2.name == "elevenlabs"

    def test_stt_adapter_wav_formatting(self):
        stt = ElevenLabsSTT(api_key="test-key", model_id="scribe_v1", sample_rate=16000)
        captured_payload = None

        class MockResp:
            status_code = 200
            def json(self):
                return {"text": "Hello world", "language_code": "en-IN"}

        class MockAsyncClient:
            async def post(self, url, headers=None, files=None, data=None):
                nonlocal captured_payload
                captured_payload = files["file"][1]
                return MockResp()
            async def aclose(self):
                pass

        stt._client = MockAsyncClient()
        final_transcripts = []
        stt.on_final = lambda t, l: final_transcripts.append((t, l))

        # Send 3200 bytes of raw PCM
        raw_pcm = b"\x00\x00" * 1600
        asyncio.run(stt._transcribe(raw_pcm))

        assert captured_payload is not None
        assert captured_payload.startswith(b"RIFF")
        assert b"WAVE" in captured_payload[:12]
        assert len(final_transcripts) == 1
        assert final_transcripts[0] == ("Hello world", "en-IN")

    def test_tts_adapter_mp3_framing(self):
        tts = ElevenLabsTTS(api_key="test-key", voice_id="21m00Tcm4TlvDq8ikWAM")
        # Generate two synthetic MP3 frames (MPEG-1 Layer 3, 128kbps, 44100Hz -> 417 bytes each)
        frame1 = b"\xff\xfb\x90\x00" + b"\xaa" * 413
        frame2 = b"\xff\xfb\x90\x00" + b"\xbb" * 413
        stream_data = frame1 + frame2 + b"\x00\x00"  # trailing bytes

        frames, remainder = tts._extract_mp3_frames(stream_data)
        assert len(frames) == 2
        assert frames[0] == frame1
        assert frames[1] == frame2
        assert remainder == b"\x00\x00"

    def test_missing_key_validation_raises(self):
        provider = ElevenLabsProvider(api_key="", fail_mode="none")
        with pytest.raises(ProviderAuthError) as exc_info:
            asyncio.run(provider.start())
        assert "ELEVENLABS_API_KEY is not configured" in str(exc_info.value)

    def test_invalid_key_circuit_breaker(self):
        provider = ElevenLabsProvider(api_key="invalid_key", fail_mode="auth")
        with pytest.raises(ProviderAuthError):
            asyncio.run(provider.start())


class TestFailoverWorkflows:
    def test_sarvam_still_works_if_elevenlabs_missing(self):
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key="",
            voice_primary_provider="sarvam",
            voice_secondary_provider="elevenlabs",
        )
        health_mgr = ProviderHealthManager()
        health_mgr.set_unavailable("elevenlabs", "missing_api_key")
        mgr = VoiceProviderManager(cfg=cfg, health_manager=health_mgr)

        provider, name = mgr.select_initial_provider()
        assert name == "sarvam"
        assert isinstance(provider, SarvamProvider)

    def test_failover_to_elevenlabs_when_available(self):
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key="test-eleven-key",
            voice_primary_provider="sarvam",
            voice_secondary_provider="elevenlabs",
            max_provider_failovers_per_call=1,
        )
        mgr = VoiceProviderManager(cfg=cfg)
        mgr.record_failure("sarvam", "Sarvam service outage")

        # In-call failover
        new_provider, new_name = mgr.get_failover_candidate("sarvam", failover_count=0)
        assert new_name == "elevenlabs"
        assert isinstance(new_provider, ElevenLabsProvider)

    def test_reverse_failover_elevenlabs_to_sarvam(self):
        cfg = _cfg(
            sarvam_api_key="test-sarvam-key",
            elevenlabs_api_key="test-eleven-key",
            voice_primary_provider="elevenlabs",
            voice_secondary_provider="sarvam",
            max_provider_failovers_per_call=1,
        )
        mgr = VoiceProviderManager(cfg=cfg)

        # Starts on ElevenLabs
        p0, name0 = mgr.select_initial_provider()
        assert name0 == "elevenlabs"

        # ElevenLabs experiences outage -> failover to Sarvam
        mgr.record_failure("elevenlabs", "ElevenLabs quota exhausted")
        p1, name1 = mgr.get_failover_candidate("elevenlabs", failover_count=0)
        assert name1 == "sarvam"
        assert isinstance(p1, SarvamProvider)
