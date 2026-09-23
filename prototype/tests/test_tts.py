"""Phase 2 TTS tests — all Sarvam API calls are mocked (zero credits)."""

import base64
import struct
import sys
import zlib
from pathlib import Path
from unittest import mock

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
from speech import tts  # noqa: E402


DUMMY_KEY = "test-dummy-key-not-a-real-secret"


def _wav_b64() -> str:
    """Minimal valid 24 kHz mono 16-bit WAV with 10 frames, base64."""
    frames = struct.pack("<10h", *range(10))
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVE"
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16)
        + b"data" + struct.pack("<I", len(frames))
    )
    return base64.b64encode(header + frames).decode()


def _cfg(**overrides):
    values = dict(
        sarvam_api_key=DUMMY_KEY,
        env_file_found=True,
        tts_model="bulbul:v3",
        tts_language="en-IN",
        tts_speaker="shreya",
        tts_sample_rate=24000,
        stt_model="saaras:v4",
        stt_language="en-IN",
        stt_mode="transcribe",
    )
    values.update(overrides)
    return config.Config(**values)


def _mock_client(audio_b64=None):
    client = mock.Mock()
    response = mock.Mock()
    response.audios = [audio_b64 if audio_b64 is not None else _wav_b64()]
    client.text_to_speech.convert.return_value = response
    return client


class TestInputValidation:
    def test_empty_text_rejected(self, tmp_path):
        with pytest.raises(tts.TTSError, match="empty"):
            tts.generate_speech("", tmp_path / "x.wav", client=_mock_client(), cfg=_cfg())
            tts.generate_speech("   ", tmp_path / "x.wav", client=_mock_client(), cfg=_cfg())

    def test_invalid_language_rejected(self, tmp_path):
        with pytest.raises(tts.TTSError, match="not supported"):
            tts.generate_speech(
                "hello", tmp_path / "x.wav", language_code="xx-XX",
                client=_mock_client(), cfg=_cfg(),
            )

    def test_invalid_speaker_rejected(self, tmp_path):
        with pytest.raises(tts.TTSError, match="not a known"):
            tts.generate_speech(
                "hello", tmp_path / "x.wav", speaker="nobody",
                client=_mock_client(), cfg=_cfg(),
            )


class TestGeneration:
    def test_success_writes_nonempty_wav(self, tmp_path):
        out = tmp_path / "nested" / "welcome.wav"
        path = tts.generate_speech(
            "Hello, welcome to Zhatura customer support.",
            out, client=_mock_client(), cfg=_cfg(),
        )
        saved = Path(path)
        assert saved == out
        assert saved.stat().st_size > 44

    def test_sdk_called_with_bulbul_v3_options(self, tmp_path):
        client = _mock_client()
        tts.generate_speech("hello", tmp_path / "x.wav", client=client, cfg=_cfg())
        kwargs = client.text_to_speech.convert.call_args.kwargs
        assert kwargs["model"] == "bulbul:v3"
        assert kwargs["speech_sample_rate"] == 24000
        assert kwargs["output_audio_codec"] == "wav"
        assert "pitch" not in kwargs and "loudness" not in kwargs

    def test_api_error_is_safe(self, tmp_path):
        client = _mock_client()
        client.text_to_speech.convert.side_effect = RuntimeError("boom")
        with pytest.raises(tts.TTSError) as excinfo:
            tts.generate_speech("hello", tmp_path / "x.wav", client=client, cfg=_cfg())
        assert DUMMY_KEY not in str(excinfo.value)

    def test_rate_limit_error(self, tmp_path):
        class RateLimited(Exception):
            status_code = 429

        client = _mock_client()
        client.text_to_speech.convert.side_effect = RateLimited("too many")
        with pytest.raises(tts.TTSError, match="rate limit"):
            tts.generate_speech("hello", tmp_path / "x.wav", client=client, cfg=_cfg())

    def test_quota_exhausted_error(self, tmp_path):
        # HTTP 402 "No credits available." must surface as an actionable
        # quota message (observed live 2026-09-22), not a generic network
        # error.
        class QuotaExhausted(Exception):
            status_code = 402

        client = _mock_client()
        client.text_to_speech.convert.side_effect = QuotaExhausted(
            "No credits available.")
        with pytest.raises(tts.TTSError, match="quota exhausted") as excinfo:
            tts.generate_speech("hello", tmp_path / "x.wav", client=client, cfg=_cfg())
        assert DUMMY_KEY not in str(excinfo.value)

    def test_no_audio_in_response(self, tmp_path):
        client = _mock_client()
        client.text_to_speech.convert.return_value = mock.Mock(audios=[])
        with pytest.raises(tts.TTSError, match="no audio"):
            tts.generate_speech("hello", tmp_path / "x.wav", client=client, cfg=_cfg())

    def test_undecodable_audio(self, tmp_path):
        with pytest.raises(tts.TTSError, match="undecodable"):
            tts.generate_speech(
                "hello", tmp_path / "x.wav",
                client=_mock_client(audio_b64=zlib.compress(b"junk").decode("latin1")[:8]),
                cfg=_cfg(),
            )

    def test_write_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "speech.audio_utils.ensure_parent_directory",
            mock.Mock(side_effect=OSError("disk full")),
        )
        with pytest.raises(tts.TTSError, match="write"):
            tts.generate_speech("hello", tmp_path / "x.wav", client=_mock_client(), cfg=_cfg())
