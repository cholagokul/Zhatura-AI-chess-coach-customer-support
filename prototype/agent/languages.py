"""Zhatura AI Customer Care — central Indian-language registry (Phase 4.1).

One authoritative description of every language the system deals with:

- what Sarvam realtime STT (saaras:v4, language_code=auto) can detect —
  all scheduled Indian languages;
- what Sarvam Bulbul v3 TTS can actually synthesize (a strict subset);
- native script names and spoken/typed aliases ("Tamizh", "Bangla", …)
  used by deterministic language-switch detection.

STT coverage > TTS coverage: Assamese, Urdu, Nepali, Konkani, Kashmiri,
Sindhi, Sanskrit, Santali, Manipuri, Bodo, Maithili and Dogri are
STT-understood but have no Bulbul v3 voice. ``supports_tts`` is the
single source of truth the telephony session consults before routing a
reply to speech — wrong-language synthesis is never silently attempted.

Note on Odia: Sarvam's API code is ``od-IN`` (ISO 639-3). The historical
``or-IN`` spelling is accepted as an alias and normalized.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str                       # BCP-47, as the Sarvam API accepts
    name: str                       # English display name
    native_name: str                # native script name
    stt_supported: bool             # saaras:v4 realtime detection
    tts_supported: bool             # bulbul:v3 synthesis
    aliases: tuple = field(default=())      # spoken/typed alternates
    code_aliases: tuple = field(default=())  # alternate BCP-47 codes


# ---------------------------------------------------------------------------
# Registry — every Sarvam scheduled language, STT first, TTS flag per
# Bulbul v3 capability.
# ---------------------------------------------------------------------------

_TTS_CODES = {"en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN",
              "ml-IN", "mr-IN", "gu-IN", "pa-IN", "od-IN"}


def _lang(code, name, native, aliases=(), code_aliases=()):
    return Language(code, name, native, True, code in _TTS_CODES,
                    aliases, code_aliases)


LANGUAGES: "tuple[Language, ...]" = (
    _lang("en-IN", "English", "English", ("anglish",)),
    _lang("hi-IN", "Hindi", "हिंदी", ("hindi", "हिन्दी", "khadi boli")),
    _lang("bn-IN", "Bengali", "বাংলা", ("bangla", "বাংলা", "বঙ্গ")),
    _lang("ta-IN", "Tamil", "தமிழ்", ("tamizh", "தமிழில்", "thamizh")),
    _lang("te-IN", "Telugu", "తెలుగు", ("telugu", "తెలుగులో")),
    _lang("kn-IN", "Kannada", "ಕನ್ನಡ", ("kanada", "ಕನ್ನಡದಲ್ಲಿ")),
    _lang("ml-IN", "Malayalam", "മലയാളം", ("malaylam", "malayali")),
    _lang("mr-IN", "Marathi", "मराठी", ("marati", "मराठीत")),
    _lang("gu-IN", "Gujarati", "ગુજરાતી", ("gujrathi", "gujarathi")),
    _lang("pa-IN", "Punjabi", "ਪੰਜਾਬੀ", ("panjabi", "punjbi")),
    # Sarvam API uses od-IN (ISO 639-3); "or-IN" accepted and normalized.
    _lang("od-IN", "Odia", "ଓଡ଼ିଆ", ("oriya", "odiya"),
          code_aliases=("or-IN",)),
    # --- STT-capable, no Bulbul v3 voice: TTS fallback policy applies ---
    _lang("as-IN", "Assamese", "অসমীয়া", ("assamiya", "axomiya")),
    _lang("ur-IN", "Urdu", "اردو", ("urdo",)),
    _lang("ne-IN", "Nepali", "नेपाली", ("nepalese", "nepali")),
    _lang("kok-IN", "Konkani", "कोंकणी", ("konkan",)),
    _lang("ks-IN", "Kashmiri", "कॉशुर", ("koshur", "ਕੋਸ਼ੁਰ")),
    _lang("sd-IN", "Sindhi", "सिंधी", ("sindhi",)),
    _lang("sa-IN", "Sanskrit", "संस्कृतम्", ("sanskritam", "संस्कृत")),
    _lang("sat-IN", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", ("santhali", "santali")),
    _lang("mni-IN", "Manipuri", "মণিপুরী", ("meitei", "meiteilon",
                                             "manipuri")),
    _lang("brx-IN", "Bodo", "बड़ो", ("boro", "बड़ा")),
    _lang("mai-IN", "Maithili", "मैथिली", ("maithali",)),
    _lang("doi-IN", "Dogri", "डोगरी", ("dogari",)),
)


_BY_CODE: "dict[str, Language]" = {}
for _language in LANGUAGES:
    _BY_CODE[_language.code] = _language
    for _alias_code in _language.code_aliases:
        _BY_CODE[_alias_code] = _language

STT_SUPPORTED_CODES = tuple(l.code for l in LANGUAGES if l.stt_supported)
TTS_SUPPORTED_CODES = tuple(l.code for l in LANGUAGES if l.tts_supported)
TTS_UNSUPPORTED_CODES = tuple(
    l.code for l in LANGUAGES if l.stt_supported and not l.tts_supported)

# Display names used in the per-turn LLM language instruction.
LANGUAGE_NAMES = {l.code: l.name for l in LANGUAGES}


def normalize_language_code(code: "str | None") -> "str | None":
    """Map alternate codes (or-IN → od-IN, case/whitespace) to the
    canonical Sarvam code; unknown codes pass through lowercased."""
    if not code:
        return code
    key = code.strip()
    if key in _BY_CODE:
        return _BY_CODE[key].code
    lowered = key.lower()
    match = _BY_CODE.get(lowered)
    return match.code if match else lowered


def get_language(code: "str | None") -> "Language | None":
    normalized = normalize_language_code(code)
    return _BY_CODE.get(normalized) if normalized else None


def language_name(code: "str | None") -> str:
    language = get_language(code)
    return language.name if language else "English"


def supports_stt(code: "str | None") -> bool:
    language = get_language(code)
    return bool(language and language.stt_supported)


def supports_tts(code: "str | None") -> bool:
    """Bulbul v3 capability check — the ONLY authority for TTS routing."""
    language = get_language(code)
    return bool(language and language.tts_supported)


def _alias_tokens(language: Language) -> "tuple[str, ...]":
    """Every Latin/script alias, lowercased, incl. native name."""
    return tuple(
        {language.name.lower(), language.native_name.lower()}
        | {a.lower() for a in language.aliases})


def match_language_alias(text: str) -> "str | None":
    """Return the language code if ``text`` mentions a known language by
    any name/alias/native word, else None.

    Pure mention-detection — NOT a switch decision (the caller must also
    express a request verb or "please"; see
    voice_agent.detect_language_switch).
    """
    import re
    lowered = text.strip().lower()
    words = set(re.findall(r"[^\s,.!?;:'\"()\[\]]+", lowered))
    padded = f" {lowered} "
    for language in LANGUAGES:
        for token in _alias_tokens(language):
            if " " in token:
                # multi-word alias: boundary match
                if f" {token} " in padded:
                    return language.code
            elif any(ord(ch) > 0x7F for ch in token):
                # script tokens never appear as substrings of other
                # languages' names
                if token in lowered:
                    return language.code
            elif token in words:
                return language.code
    return None
