"""Zhatura AI Customer Care — optional microphone helper (Phase 2).

Records a short WAV from the local microphone for STT testing.

This is NOT the Phase 3 realtime voice agent — just a manual helper:

    Microphone → short WAV → save → Sarvam STT

Requires the optional ``sounddevice`` dependency. If it is not
installed, ``record_wav`` fails with a clear message and nothing else
in the project is affected.
"""

from __future__ import annotations

import logging
import wave
from pathlib import Path

from . import audio_utils

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_DURATION_SECONDS = 5
MIC_PERMISSION_HINT = (
    "Microphone access is required.\n\n"
    "macOS:\n"
    "System Settings\n"
    "→ Privacy & Security\n"
    "→ Microphone\n"
    "→ Enable access for Terminal"
)


class MicrophoneError(Exception):
    """Raised when microphone recording is unavailable or fails."""


class MicrophoneStreamer:
    """Async microphone capture at 16 kHz mono int16 for realtime STT.

    Audio chunks are placed on an ``asyncio.Queue`` as raw PCM bytes.
    ``start()`` raises MicrophoneError with macOS permission guidance if
    the device cannot be opened.
    """

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE,
                 chunk_ms: int = 100):
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.queue = None
        self._stream = None

    def start(self, loop) -> "asyncio.Queue":
        import asyncio
        import queue as thread_queue

        try:
            import sounddevice as sd
        except ImportError:
            raise MicrophoneError(
                "Microphone streaming requires 'sounddevice': "
                "pip install sounddevice"
            ) from None

        self.queue = asyncio.Queue()
        raw = thread_queue.Queue()

        def callback(indata, frames, _time, status):  # noqa: ANN001
            raw.put(bytes(indata))

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=int(self.sample_rate * self.chunk_ms / 1000),
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            raise MicrophoneError(
                f"Could not open microphone ({type(exc).__name__}).\n\n"
                + MIC_PERMISSION_HINT
            ) from None

        async def _pump():
            while True:
                try:
                    chunk = await loop.run_in_executor(None, raw.get)
                except Exception:
                    return
                await self.queue.put(chunk)

        self._pump_task = asyncio.ensure_future(_pump(), loop=loop)
        logger.info("Microphone streaming started (%d Hz, %d ms chunks).",
                    self.sample_rate, self.chunk_ms)
        return self.queue

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        task = getattr(self, "_pump_task", None)
        if task is not None:
            task.cancel()
        logger.info("Microphone streaming stopped.")


def check_microphone_available() -> "tuple[bool, str]":
    """Try to open the default input device briefly.

    Returns (ok, message). ``ok=False`` messages contain macOS
    permission guidance.
    """
    try:
        import sounddevice as sd
    except ImportError:
        return False, "sounddevice is not installed."
    # Distinguish "no mic hardware" from "mic exists but blocked" —
    # the fixes are completely different.
    try:
        devices = sd.query_devices()
        inputs = [d for d in devices
                  if isinstance(d, dict) and d.get("max_input_channels", 0) > 0]
    except Exception:
        inputs = []
    if not inputs:
        return False, (
            "No microphone input device found on this Mac.\n\n"
            "Connect an external microphone (USB mic, headset, or "
            "AirPods), then re-run. After connecting, macOS may also ask "
            "for microphone permission:\n\n" + MIC_PERMISSION_HINT
        )
    try:
        with sd.InputStream(samplerate=DEFAULT_SAMPLE_RATE, channels=1,
                            dtype="int16", blocksize=512):
            pass
    except Exception as exc:
        return False, (
            f"Microphone unavailable ({type(exc).__name__}).\n\n"
            + MIC_PERMISSION_HINT
        )
    return True, "Microphone ready."


def record_wav(
    output_path: "str | Path",
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> str:
    """Record ``duration_seconds`` of mono audio and save as 16-bit WAV.

    Raises:
        MicrophoneError: if sounddevice is missing or recording fails.
    """
    try:
        import sounddevice as sd  # optional dependency, imported lazily
    except ImportError:
        raise MicrophoneError(
            "Microphone recording requires the optional 'sounddevice' "
            "package: pip install sounddevice"
        ) from None

    if duration_seconds <= 0:
        raise MicrophoneError("Recording duration must be positive.")

    out = audio_utils.ensure_parent_directory(output_path)
    logger.info("Recording %ds at %d Hz from default microphone...",
                duration_seconds, sample_rate)
    try:
        audio = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()
    except Exception as exc:
        raise MicrophoneError(
            f"Microphone recording failed ({type(exc).__name__}) — "
            "check the macOS microphone permission for this terminal."
        ) from None

    try:
        with wave.open(str(out), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio.tobytes())
    except OSError as exc:
        raise MicrophoneError(f"Could not write WAV file: {exc}") from None

    logger.info("Recording saved to %s.", out)
    return str(out)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m prototype.speech.microphone",
        description="Record a short WAV from the local microphone (Phase 2 helper).",
    )
    parser.add_argument("--output", required=True, help="Output .wav path.")
    parser.add_argument("--seconds", type=int, default=DEFAULT_DURATION_SECONDS)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        path = record_wav(args.output, args.seconds)
    except MicrophoneError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Recording saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
