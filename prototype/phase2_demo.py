"""Zhatura AI Customer Care — Phase 2 live acceptance demo.

⚠ Makes REAL Sarvam API calls (a few, tiny). Not run by pytest.

Pipeline under test:

    TEXT → Sarvam TTS → WAV file → Sarvam STT → transcript

Usage:

    python prototype/phase2_demo.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from speech import audio_utils, stt, tts  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_WAV = PROJECT_ROOT / "audio_samples" / "sarvam" / "english" / "phase2_demo.wav"

TEST_TEXT = "Hello, welcome to Zhatura customer support."
Z_KEYTERMS = ["Zhatura", "Zhatura AI", "AI Chess Coach", "Chess Academy"]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logger = logging.getLogger("phase2.demo")

    print("Zhatura AI Customer Care — Phase 2 Speech Demo")
    print("=" * 52)

    try:
        cfg = config.load_config()
    except config.ConfigurationError as exc:
        print(exc)
        return 1
    logger.info("Configuration loaded (TTS=%s, STT=%s).", cfg.tts_model, cfg.stt_model)

    # 1) TTS
    try:
        wav_path = tts.generate_speech(TEST_TEXT, DEMO_WAV, cfg=cfg)
    except tts.TTSError as exc:
        print(f"TTS FAILED: {exc}")
        print("\nPhase 2 Speech Pipeline:\nFAIL")
        return 1

    meta = audio_utils.wav_metadata(wav_path)
    print(f"Original Text:\n{TEST_TEXT}\n")
    print(f"Generated Audio:\n{wav_path}")
    print(f"  {meta['duration_seconds']}s, {meta['sample_rate_hz']} Hz, "
          f"{meta['channels']}ch\n")

    # 2) STT (with and without Zhatura keyterms)
    try:
        plain = stt.transcribe_audio_full(wav_path, cfg=cfg)
        with_terms = stt.transcribe_audio_full(wav_path, cfg=cfg, keyterms=Z_KEYTERMS)
    except stt.STTError as exc:
        print(f"STT FAILED: {exc}")
        print("\nPhase 2 Speech Pipeline:\nFAIL")
        return 1

    print("Transcript:")
    print(plain.transcript or "(empty)")
    print()
    print("Transcript (Zhatura keyterms):")
    print(with_terms.transcript or "(empty)")
    print()

    brand_ok = "zhatura" in plain.transcript.lower()
    passed = bool(plain.transcript) and "welcome" in plain.transcript.lower()
    print("Phase 2 Speech Pipeline:")
    print("PASS" if passed else "FAIL")
    print(f"Zhatura brand recognized: {'YES' if brand_ok else 'NO'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
