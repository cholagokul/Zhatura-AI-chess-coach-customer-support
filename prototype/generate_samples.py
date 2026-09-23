"""Zhatura AI Customer Care — Phase 2 sample generator (LIVE).

Generates the reusable Sarvam TTS test set under ``audio_samples/sarvam/``
from the sentence definitions in ``audio_samples/sentences.md``.

⚠ This script makes REAL Sarvam API calls. Run it intentionally:

    python prototype/generate_samples.py            # skip existing files
    python prototype/generate_samples.py --force    # regenerate everything

It is never executed by pytest.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from speech import tts  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT_ROOT / "audio_samples" / "sarvam"

# (language folder, sample key, text) — mirrors audio_samples/sentences.md
CORPUS = [
    # English
    ("english", "welcome", "Hello, welcome to Zhatura customer support. How can I help you today?"),
    ("english", "account_help", "I can help you check your child's Zhatura account."),
    ("english", "problem", "Please tell me what problem you are experiencing."),
    ("english", "subscription", "Your subscription status has been checked."),
    ("english", "human_transfer", "Would you like me to connect you with a human support representative?"),
    # Tamil
    ("tamil", "welcome", "வணக்கம், Zhatura கஸ்டமர் சப்போர்டுக்கு வரவேற்கிறோம். இன்று உங்களுக்கு எப்படி உதவ முடியும்?"),
    ("tamil", "account_help", "உங்கள் குழந்தையின் Zhatura அக்கவுண்டை செக் செய்ய நான் உதவ முடியும்."),
    ("tamil", "problem", "நீங்கள் என்ன பிராப்ளம் அனுபவிக்கிறீர்கள் என்று சொல்லுங்கள்."),
    # Hindi
    ("hindi", "welcome", "नमस्ते, Zhatura कस्टमर सपोर्ट में आपका स्वागत है। आज मैं आपकी कैसे मदद कर सकती हूँ?"),
    ("hindi", "account_help", "मैं आपके बच्चे के Zhatura अकाउंट की जाँच करने में मदद कर सकती हूँ।"),
    ("hindi", "problem", "कृपया बताइए आपको क्या समस्या आ रही है।"),
    # Hinglish (spoken Hindi, Latin script)
    ("hinglish", "welcome", "Namaste, Zhatura customer support mein aapka swagat hai. Main aapki kaise help kar sakti hoon?"),
    ("hinglish", "account_help", "Main aapke bachche ka Zhatura account check karne mein help kar sakti hoon."),
    # Tanglish (spoken Tamil, Latin script)
    ("tanglish", "welcome", "Vanakkam, Zhatura customer support-ku varaverkirom. Unakkum enna help venum?"),
    ("tanglish", "account_help", "Unga kozhandhai-yoda Zhatura account-a check panna naan help panna mudiyum."),
    # Zhatura brand terminology
    ("terminology", "brand_zhatura", "Zhatura"),
    ("terminology", "brand_zhatura_ai", "Zhatura AI is our learning platform."),
    ("terminology", "brand_chess_coach", "Your child uses the Zhatura AI Chess Coach."),
    ("terminology", "brand_parent_dashboard", "You can view progress in the Parent Dashboard."),
    ("terminology", "brand_coach_dashboard", "Coaches manage batches in the Coach Dashboard."),
    ("terminology", "brand_student_dashboard", "Students log in through the Student Dashboard."),
    ("terminology", "brand_chess_academy", "Welcome to the Zhatura Chess Academy."),
]

LANGUAGE_CODES = {
    "english": "en-IN",
    "tamil": "ta-IN",
    "hindi": "hi-IN",
    "hinglish": "hi-IN",
    "tanglish": "ta-IN",
    "terminology": "en-IN",
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing sample files.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    generated, skipped, failed = 0, 0, 0
    for language, key, text in CORPUS:
        path = SAMPLES / language / f"{key}.wav"
        if path.exists() and not args.force:
            logging.getLogger("samples").info("SKIP (exists): %s", path.name)
            skipped += 1
            continue
        try:
            tts.generate_speech(
                text=text,
                output_path=path,
                language_code=LANGUAGE_CODES[language],
            )
            generated += 1
        except tts.TTSError as exc:
            logging.getLogger("samples").error("FAILED %s/%s: %s", language, key, exc)
            failed += 1

    print(f"\nGenerated: {generated}  Skipped: {skipped}  Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
