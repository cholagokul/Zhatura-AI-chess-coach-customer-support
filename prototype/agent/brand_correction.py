"""Zhatura AI Customer Care — transcript brand correction (Phase 3).

Phase 2/3 findings: Sarvam STT (batch keyterms AND realtime prompt)
does not reliably recognize the brand "Zhatura" in realtime mode.
Observed realtime mishearings (from live tests, 2026-09-21):

    Jhatura, Jathura, Jatura, JATURA, Jatuara, Zhathura, ...
    Hindi: जतुरा, झतूरा, जंतुरा
    Tamil: ஜெத்துரா, ஜத்துரா, ஜாத்துரா, ஜதுரா

Batch STT keyterms fixed 7/7; realtime `prompt` fixed 0/3 prompt
formats on saaras:v4 (fast + balanced) and saaras:v3-realtime.

This module deterministically corrects known brand mishearings in
FINAL transcripts before they reach the LLM. Corrections are logged.
The term list is config-driven (SARVAM_STT_PROMPT); mishearing variants
live here in one place only.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Observed + phonetically plausible mishearings of "Zhatura".
_BRAND_VARIANTS = [
    "jhatoora", "jathoora", "jhathura", "zhathura", "jhatura",
    "jathura", "jatuara", "jatoora", "zapura", "jatura",
    "zathura", "jatora", "zatura", "jathra",
    # Live-observed (Phase 4.1/5 calls): "Hedura", dropped-initial
    # "atura". Word-boundary regex keeps them from touching real words.
    "hedura", "atura",
    # Hindi (Devanagari) — observed live in Phase 3 runs.
    "जंतुरा", "झतूरा", "जतुरा",
    # Tamil — observed live in Phase 3 runs.
    "ஜெத்துரா", "ஜாத்துரா", "ஜத்துரா", "ஜதுரா",
    # Telugu — observed live on the Phase 5 multilingual call.
    "జతురా", "ఝతురా", "జాతురా", "ఝాతురా",
]
_BRAND_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(sorted(set(_BRAND_VARIANTS), key=len, reverse=True)) + r")(?!\w)",
    re.IGNORECASE,
)


def correct_brand_terms(text: str) -> str:
    """Return ``text`` with known brand mishearings replaced by 'Zhatura'.

    The original user wording is otherwise preserved. This affects only
    final transcripts; partials are shown raw for debugging.
    """
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        logger.info("Brand correction: '%s' → 'Zhatura'", match.group(0))
        return "Zhatura"

    return _BRAND_RE.sub(_replace, text)


def matches_spoken_echo(transcript: str, spoken_text: str,
                        min_overlap: float = 0.6) -> bool:
    """True if ``transcript`` likely is the agent's own TTS echoed back.

    Simple word-overlap heuristic for local-prototype echo protection
    (headphones remain the recommended clean-test setup).
    """
    if not transcript.strip() or not spoken_text.strip():
        return False
    heard = set(re.findall(r"[a-z]+", transcript.lower()))
    spoken = set(re.findall(r"[a-z]+", spoken_text.lower()))
    if not spoken:
        return False
    overlap = len(heard & spoken) / len(spoken)
    return overlap >= min_overlap
