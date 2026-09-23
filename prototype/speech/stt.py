"""Zhatura AI Customer Care — Sarvam Speech-to-Text (Phase 2).

Prerecorded-audio transcription via the official ``sarvamai`` SDK
(``client.speech_to_text.transcribe``) using model ``saaras:v4`` in
``transcribe`` mode. Realtime streaming STT is Phase 3+ and is not
implemented here.

The API key is never printed, logged, or included in errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

try:  # support both package import and direct execution
    from .. import config as _config_module
    from ..sarvam_client import get_sarvam_client
    from . import audio_utils
    from .tts import _safe_api_error
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as _config_module
    from sarvam_client import get_sarvam_client
    from speech import audio_utils
    from speech.tts import _safe_api_error

logger = logging.getLogger(__name__)

SAARAS_LANGUAGES = {
    "unknown", "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN",
    "pa-IN", "ta-IN", "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN",
    "ne-IN", "kok-IN", "ks-IN", "sd-IN", "sa-IN", "sat-IN", "mni-IN",
    "brx-IN", "mai-IN", "doi-IN",
}

SAARAS_MODES = {"transcribe", "translate", "verbatim", "translit", "codemix"}


class STTError(Exception):
    """Raised for STT input, API, or unsupported-file failures."""


@dataclass
class TranscriptionResult:
    """Structured STT result. Never contains credentials."""

    transcript: str
    language_code: "str | None" = None
    language_probability: "float | None" = None
    keyterms_used: list = field(default_factory=list)


def transcribe_audio_full(
    file_path: "str | Path",
    language_code: "str | None" = None,
    mode: "str | None" = None,
    *,
    keyterms: "list[str] | None" = None,
    client=None,
    cfg=None,
) -> TranscriptionResult:
    """Transcribe a WAV file with Sarvam saaras:v4 and return details.

    Args:
        file_path: Path to a ``.wav`` file.
        language_code: BCP-47 code or ``unknown`` (default from config).
        mode: saaras mode, default ``transcribe``.
        keyterms: Optional terminology hints (e.g. ``["Zhatura"]``).
        client / cfg: Optional injected client/config (used by tests).

    Raises:
        STTError: for missing/invalid files, invalid options, or API
            failures. Messages never contain the API key.
    """
    if cfg is None:
        cfg = _config_module.load_config()

    try:
        path = audio_utils.validate_input_file(file_path)
    except audio_utils.AudioValidationError as exc:
        raise STTError(str(exc)) from None

    language_code = language_code or cfg.stt_language
    mode = mode or cfg.stt_mode

    if language_code not in SAARAS_LANGUAGES:
        raise STTError(f"Language '{language_code}' is not supported by saaras.")
    if mode not in SAARAS_MODES:
        raise STTError(f"Mode '{mode}' is not supported by saaras.")

    if client is None:
        client = get_sarvam_client(cfg)

    logger.info("STT request started (model=%s, lang=%s, mode=%s, keyterms=%d).",
                cfg.stt_model, language_code, mode, len(keyterms or []))
    try:
        with open(path, "rb") as audio_file:
            response = client.speech_to_text.transcribe(
                file=audio_file,
                model=cfg.stt_model,
                mode=mode,
                language_code=language_code,
                input_audio_codec="wav",
                keyterms=keyterms if keyterms else None,
            )
    except Exception as exc:
        raise STTError(_safe_api_error(exc, "STT")) from None

    transcript = (getattr(response, "transcript", None) or "").strip()
    result = TranscriptionResult(
        transcript=transcript,
        language_code=getattr(response, "language_code", None),
        language_probability=getattr(response, "language_probability", None),
        keyterms_used=list(keyterms or []),
    )
    logger.info("STT transcription succeeded (%d characters).", len(transcript))
    return result


def transcribe_audio(
    file_path: "str | Path",
    language_code: "str | None" = None,
    mode: "str | None" = None,
    **kwargs,
) -> str:
    """Transcribe a WAV file and return only the transcript text."""
    return transcribe_audio_full(
        file_path, language_code, mode, **kwargs
    ).transcript


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m prototype.speech.stt",
        description="Transcribe a WAV file with Sarvam saaras (Phase 2).",
    )
    parser.add_argument("--input", required=True, help="Input .wav path.")
    parser.add_argument("--language", default=None, help="e.g. en-IN, ta-IN, hi-IN, unknown")
    parser.add_argument("--mode", default=None, help="transcribe (default)")
    parser.add_argument("--keyterms", default=None,
                        help="Comma-separated terminology hints, e.g. 'Zhatura,AI Chess Coach'")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    keyterms = [k.strip() for k in args.keyterms.split(",")] if args.keyterms else None
    try:
        result = transcribe_audio_full(
            args.input, args.language, args.mode, keyterms=keyterms
        )
    except (_config_module.ConfigurationError, STTError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Transcript: {result.transcript or '(empty)'}")
    if result.language_code:
        print(f"Language:   {result.language_code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
