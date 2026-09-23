"""Zhatura AI Customer Care — Sarvam Text-to-Speech (Phase 2).

Wraps the official ``sarvamai`` SDK TTS call
(``client.text_to_speech.convert``), decodes the returned base64 audio,
and saves it to disk. Bulbul v3 is used; Bulbul v2-only parameters
(pitch, loudness) are intentionally not exposed.

The API key is never printed, logged, or included in errors.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

try:  # support both package import and `python prototype/speech/tts.py`
    from .. import config as _config_module
    from ..sarvam_client import get_sarvam_client
    from . import audio_utils
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as _config_module
    from sarvam_client import get_sarvam_client
    from speech import audio_utils

logger = logging.getLogger(__name__)

# Bulbul v3 voices exposed by the installed SDK (kept for validation).
BULBUL_V3_SPEAKERS = {
    "anushka", "abhilash", "manisha", "vidya", "arya", "karun", "hitesh",
    "aditya", "ritu", "priya", "neha", "rahul", "pooja", "rohan", "simran",
    "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun", "manan",
    "sumit", "roopa", "kabir", "aayan", "shubh", "ashutosh", "advait",
    "anand", "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti",
    "suhani", "mohit", "kavitha", "rehan", "soham", "rupali",
}

BULBUL_V3_LANGUAGES = {
    "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN",
    "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN",
}


class TTSError(Exception):
    """Raised for TTS input, API, or file-write failures."""


def generate_speech(
    text: str,
    output_path: "str | Path",
    language_code: "str | None" = None,
    speaker: "str | None" = None,
    *,
    client=None,
    cfg=None,
) -> str:
    """Generate speech with Sarvam Bulbul v3 and save it as WAV.

    Args:
        text: Text to synthesize (must be non-empty).
        output_path: Destination ``.wav`` path (parents are created).
        language_code: BCP-47 code, e.g. ``en-IN`` (default from config).
        speaker: Bulbul v3 voice name (default from config).
        client: Optional pre-built Sarvam client (used by tests).
        cfg: Optional pre-loaded config (used by tests).

    Returns:
        The saved file path as a string.

    Raises:
        TTSError: for invalid input, API failures, or write failures.
            Messages never contain the API key.
    """
    if cfg is None:
        cfg = _config_module.load_config()

    text = (text or "").strip()
    if not text:
        raise TTSError("TTS input text is empty.")

    language_code = language_code or cfg.tts_language
    speaker = speaker or cfg.tts_speaker

    if language_code not in BULBUL_V3_LANGUAGES:
        raise TTSError(
            f"Language '{language_code}' is not supported by Bulbul v3."
        )
    if speaker not in BULBUL_V3_SPEAKERS:
        raise TTSError(
            f"Speaker '{speaker}' is not a known Bulbul v3 voice."
        )

    if client is None:
        client = get_sarvam_client(cfg)

    logger.info("TTS request started (model=%s, lang=%s, speaker=%s).",
                cfg.tts_model, language_code, speaker)
    try:
        response = client.text_to_speech.convert(
            text=text,
            language_code=language_code,
            speaker=speaker,
            model=cfg.tts_model,
            speech_sample_rate=cfg.tts_sample_rate,
            output_audio_codec="wav",
            enable_preprocessing=True,
        )
    except Exception as exc:
        raise TTSError(_safe_api_error(exc, "TTS")) from None

    audios = getattr(response, "audios", None) or []
    if not audios or not audios[0]:
        raise TTSError("TTS API returned no audio data.")

    try:
        audio_bytes = base64.b64decode(audios[0])
    except Exception:
        raise TTSError("TTS API returned undecodable audio data.") from None

    try:
        out = audio_utils.ensure_parent_directory(output_path)
        out.write_bytes(audio_bytes)
    except OSError as exc:
        raise TTSError(f"Could not write audio file: {exc.strerror or exc}") from None

    logger.info("TTS generation succeeded — audio saved to %s (%d bytes).",
                out, len(audio_bytes))
    return str(out)


def _safe_api_error(exc: Exception, operation: str) -> str:
    """Map an SDK exception to a safe, readable message (no secrets)."""
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return f"Sarvam {operation} authentication failure (invalid or expired API key)."
    if status == 402:
        return (f"Sarvam {operation} quota exhausted — the account has no "
                f"credits. Top up the Sarvam subscription and retry.")
    if status == 429:
        return f"Sarvam {operation} rate limit reached — try again shortly."
    if status is not None and 500 <= status < 600:
        return f"Sarvam {operation} service error (HTTP {status}) — try again later."
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if any(w in name or w in message for w in ("connect", "timeout", "network", "unreachable")):
        return f"Sarvam {operation} network/connectivity failure."
    return f"Sarvam {operation} request failed ({type(exc).__name__})."


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m prototype.speech.tts",
        description="Generate a Sarvam TTS WAV sample (Phase 2).",
    )
    parser.add_argument("--text", required=True, help="Text to synthesize.")
    parser.add_argument("--output", required=True, help="Output .wav path.")
    parser.add_argument("--language", default=None, help="e.g. en-IN, ta-IN, hi-IN")
    parser.add_argument("--speaker", default=None, help="Bulbul v3 voice name")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        path = generate_speech(
            text=args.text,
            output_path=args.output,
            language_code=args.language,
            speaker=args.speaker,
        )
    except (_config_module.ConfigurationError, TTSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Audio saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
