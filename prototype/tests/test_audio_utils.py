"""Phase 2 audio-utils tests — no API involvement."""

import struct
import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from speech import audio_utils  # noqa: E402


def _write_wav(path: Path, rate: int = 24000, frames: int = 2400) -> Path:
    data = struct.pack(f"<{frames}h", *([0] * frames))
    header = (
        b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", len(data))
    )
    path.write_bytes(header + data)
    return path


class TestDirectories:
    def test_ensure_directory_creates_nested(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        audio_utils.ensure_directory(target)
        assert target.is_dir()

    def test_ensure_parent_directory(self, tmp_path):
        file_path = tmp_path / "x" / "y" / "file.wav"
        audio_utils.ensure_parent_directory(file_path)
        assert file_path.parent.is_dir()


class TestValidation:
    def test_valid_wav_accepted(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav")
        assert audio_utils.validate_input_file(wav) == wav

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(audio_utils.AudioValidationError, match="not found"):
            audio_utils.validate_input_file(tmp_path / "none.wav")

    def test_wrong_type_rejected(self, tmp_path):
        mp3 = tmp_path / "a.mp3"
        mp3.write_bytes(b"x" * 100)
        with pytest.raises(audio_utils.AudioValidationError, match="Unsupported"):
            audio_utils.validate_input_file(mp3)

    def test_tiny_file_rejected(self, tmp_path):
        tiny = tmp_path / "tiny.wav"
        tiny.write_bytes(b"RIFF")
        with pytest.raises(audio_utils.AudioValidationError, match="empty or corrupt"):
            audio_utils.validate_input_file(tiny)


class TestMetadata:
    def test_wav_metadata(self, tmp_path):
        wav = _write_wav(tmp_path / "ok.wav", rate=24000, frames=2400)
        meta = audio_utils.wav_metadata(wav)
        assert meta["sample_rate_hz"] == 24000
        assert meta["channels"] == 1
        assert meta["duration_seconds"] == pytest.approx(0.1)

    def test_wav_metadata_invalid(self, tmp_path):
        bad = tmp_path / "bad.wav"
        bad.write_bytes(b"not a wave file but long enough to pass size check" * 2)
        with pytest.raises(audio_utils.AudioValidationError, match="WAV"):
            audio_utils.wav_metadata(bad)


class TestSafeName:
    def test_slug(self):
        assert audio_utils.safe_name("Hello, Welcome to Zhatura!") == "hello_welcome_to_zhatura"

    def test_empty_slug_fallback(self):
        assert audio_utils.safe_name("!!!") == "sample"
