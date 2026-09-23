"""Phase 2 STT tests — all Sarvam API calls are mocked (zero credits)."""

import struct
import sys
from pathlib import Path
from unittest import mock

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
from speech import stt  # noqa: E402


DUMMY_KEY = "test-dummy-key-not-a-real-secret"


def _write_wav(path: Path, frames: int = 10) -> Path:
    data = struct.pack(f"<{frames}h", *([0] * frames))
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16)
        + b"data" + struct.pack("<I", len(data))
    )
    path.write_bytes(header + data)
    return path


def _cfg():
    return config.Config(
        sarvam_api_key=DUMMY_KEY,
        env_file_found=True,
        stt_model="saaras:v4",
        stt_language="en-IN",
        stt_mode="transcribe",
    )


def _mock_client(transcript="Hello, welcome to Zhatura customer support."):
    client = mock.Mock()
    response = mock.Mock()
    response.transcript = transcript
    response.language_code = "en-IN"
    response.language_probability = 0.99
    client.speech_to_text.transcribe.return_value = response
    return client


class TestInputValidation:
    def test_missing_file(self, tmp_path):
        with pytest.raises(stt.STTError, match="not found"):
            stt.transcribe_audio(tmp_path / "nope.wav", client=_mock_client(), cfg=_cfg())

    def test_unsupported_extension(self, tmp_path):
        mp3 = tmp_path / "a.mp3"
        mp3.write_bytes(b"x" * 100)
        with pytest.raises(stt.STTError, match="Unsupported"):
            stt.transcribe_audio(mp3, client=_mock_client(), cfg=_cfg())

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.wav"
        empty.write_bytes(b"")
        with pytest.raises(stt.STTError, match="empty or corrupt"):
            stt.transcribe_audio(empty, client=_mock_client(), cfg=_cfg())

    def test_invalid_language(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        with pytest.raises(stt.STTError, match="not supported"):
            stt.transcribe_audio(wav, "xx-XX", client=_mock_client(), cfg=_cfg())

    def test_invalid_mode(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        with pytest.raises(stt.STTError, match="not supported"):
            stt.transcribe_audio(wav, mode="bogus", client=_mock_client(), cfg=_cfg())


class TestTranscription:
    def test_success_returns_transcript(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        text = stt.transcribe_audio(wav, client=_mock_client(), cfg=_cfg())
        assert text == "Hello, welcome to Zhatura customer support."

    def test_full_result_has_language_and_keyterms(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        result = stt.transcribe_audio_full(
            wav, keyterms=["Zhatura"], client=_mock_client(), cfg=_cfg()
        )
        assert result.language_code == "en-IN"
        assert result.keyterms_used == ["Zhatura"]

    def test_sdk_called_with_saaras_v4_options(self, tmp_path):
        client = _mock_client()
        wav = _write_wav(tmp_path / "ok.wav")
        stt.transcribe_audio(wav, client=client, cfg=_cfg())
        kwargs = client.speech_to_text.transcribe.call_args.kwargs
        assert kwargs["model"] == "saaras:v4"
        assert kwargs["mode"] == "transcribe"
        assert kwargs["input_audio_codec"] == "wav"

    def test_empty_transcript(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        text = stt.transcribe_audio(
            wav, client=_mock_client(transcript=None), cfg=_cfg()
        )
        assert text == ""

    def test_api_error_is_safe(self, tmp_path):
        client = _mock_client()
        client.speech_to_text.transcribe.side_effect = RuntimeError("boom")
        wav = _write_wav(tmp_path / "ok.wav")
        with pytest.raises(stt.STTError) as excinfo:
            stt.transcribe_audio(wav, client=client, cfg=_cfg())
        assert DUMMY_KEY not in str(excinfo.value)

    def test_auth_failure_classified(self, tmp_path):
        class Forbidden(Exception):
            status_code = 403

        client = _mock_client()
        client.speech_to_text.transcribe.side_effect = Forbidden("403")
        wav = _write_wav(tmp_path / "ok.wav")
        with pytest.raises(stt.STTError, match="authentication failure"):
            stt.transcribe_audio(wav, client=client, cfg=_cfg())
