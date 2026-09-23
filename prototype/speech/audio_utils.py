"""Zhatura AI Customer Care — audio utilities (Phase 2).

Small helpers only: existence/type validation, directory creation,
safe naming, and basic WAV metadata. No audio-processing framework.
"""

from __future__ import annotations

import re
import wave
from contextlib import closing
from pathlib import Path


class AudioValidationError(Exception):
    """Raised when an audio path or file is not usable."""


def ensure_directory(path: "str | Path") -> Path:
    """Create a directory (and parents) if needed; return it as Path."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ensure_parent_directory(file_path: "str | Path") -> Path:
    """Ensure the parent directory of ``file_path`` exists; return Path."""
    path = Path(file_path)
    ensure_directory(path.parent)
    return path


def validate_input_file(file_path: "str | Path", suffixes=(".wav",)) -> Path:
    """Validate an audio file for STT input.

    Raises AudioValidationError when the file is missing, empty, corrupt,
    or has an unsupported extension. Phase 2 prioritizes WAV.
    """
    path = Path(file_path)
    if not path.is_file():
        raise AudioValidationError(f"Audio file not found: {path}")
    if path.suffix.lower() not in suffixes:
        raise AudioValidationError(
            f"Unsupported audio type '{path.suffix}'. "
            f"Supported in Phase 2: {', '.join(suffixes)}"
        )
    if path.stat().st_size <= 44:  # WAV header alone implies no audio body
        raise AudioValidationError(f"Audio file is empty or corrupt: {path}")
    return path


def wav_metadata(file_path: "str | Path") -> dict:
    """Return basic WAV metadata (channels, sample rate, duration)."""
    path = validate_input_file(file_path)
    try:
        with closing(wave.open(str(path), "rb")) as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return {
                "channels": wav.getnchannels(),
                "sample_rate_hz": rate,
                "sample_width_bytes": wav.getsampwidth(),
                "frames": frames,
                "duration_seconds": round(frames / float(rate), 3)
                if rate
                else 0.0,
            }
    except wave.Error as exc:
        raise AudioValidationError(f"Not a readable WAV file: {path}") from None


_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def safe_name(text: str, max_length: int = 60) -> str:
    """Turn free text into a lowercase, filesystem-safe slug."""
    slug = _SLUG_UNSAFE.sub("_", text.strip().lower()).strip("_")
    return slug[:max_length] or "sample"
