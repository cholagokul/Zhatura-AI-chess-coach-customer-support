# PHASE 4.1 REPORT — Sarvam Multilingual Expansion

Date: 2026-09-22
Scope: expand the Phase 4 Exotel + Sarvam voice agent from
English/Tamil/Hindi (manual whitelist) to Sarvam's full scheduled
Indian-language coverage. The working Phase 4 telephony architecture
(paced audio, barge-in, end-call, cleanup, registry defense) is
unchanged except for the language subsystem.

## 1. Supported STT Languages (saaras:v4 realtime, `language_code=auto`)

All **23 scheduled languages** are handled — detected language is read
from every STT final and stored per call:

English `en-IN` · Hindi `hi-IN` · Bengali `bn-IN` · Tamil `ta-IN` ·
Telugu `te-IN` · Kannada `kn-IN` · Malayalam `ml-IN` · Marathi `mr-IN` ·
Gujarati `gu-IN` · Punjabi `pa-IN` · Odia `od-IN`¹ · Assamese `as-IN` ·
Urdu `ur-IN` · Nepali `ne-IN` · Konkani `kok-IN` · Kashmiri `ks-IN` ·
Sindhi `sd-IN` · Sanskrit `sa-IN` · Santali `sat-IN` · Manipuri `mni-IN` ·
Bodo `brx-IN` · Maithili `mai-IN` · Dogri `doi-IN`

No five-language whitelist remains anywhere in the code.

¹ Odia: Sarvam's API accepts `od-IN` (ISO 639-3); the historical
`or-IN` spelling is accepted as an alias and normalized.

## 2. Supported TTS Languages (Bulbul v3)

**11 languages have a Bulbul v3 voice** — full voice support (STT + LLM
reply + spoken TTS) applies only to these:

en-IN · hi-IN · bn-IN · ta-IN · te-IN · kn-IN · ml-IN · mr-IN ·
gu-IN · pa-IN · od-IN

The other 12 STT languages (Assamese, Urdu, Nepali, Konkani, Kashmiri,
Sindhi, Sanskrit, Santali, Manipuri, Bodo, Maithili, Dogri) are
**understood but not spoken** — see §6.

## 3. Language Registry

Single source of truth: `prototype/agent/languages.py` — one registry
entry per language with display name, BCP-47 code, `stt_supported`,
`tts_supported`, native script name, spoken/typed aliases
("Tamizh", "Bangla", "বাংলা", "मराठी", …), and code aliases
(`or-IN → od-IN`). Consumers: `supports_stt()`, `supports_tts()`,
`match_language_alias()`, `normalize_language_code()`,
`language_name()`.

## 4. Detected-Language Tests

- Automated: registry completeness (23 STT codes), Bulbul TTS set (11),
  unsupported set (exactly 12), code-alias normalization, every name /
  native name present.
- Live (real Sarvam, simulated Exotel): STT auto-detection from native
  audio fixtures synthesized with Bulbul v3 per language — results in
  the per-language table below.

## 5. Language-Switching Tests

Deterministic, verb-aware switch detection (mention alone — "I am
learning Tamil", "Kannada chess lessons" — never switches):

| Request (as spoken) | Detected |
|---|---|
| "Speak Tamil" | ta-IN |
| "Can you speak Bengali?" | bn-IN |
| "Please continue in Telugu" | te-IN |
| "Kannada please" | kn-IN |
| "Hindi mein baat karo" | hi-IN |
| "தமிழில் பேச முடியுமா?" | ta-IN |
| "Can we switch to Bangla?" | bn-IN |
| "Please switch to Urdu" | ur-IN |
| "Can you switch back to English?" | en-IN |

Switching is immediate and per call only (`requested_language` sticky
until the caller explicitly switches again — so code-mixed turns don't
yank the language back). Every switch is logged
(`LANGUAGE SWITCH REQUEST: <code>`).

## 6. Unsupported-TTS Fallback Behavior

Router: `supports_tts(language_code) -> bool` — the single authority;
the session routes every reply through it before Bulbul.

When false (the 12 voice-less languages):

1. STT recognition and conversation language detection keep working.
2. Logged once per language per call:
   `TTS_UNAVAILABLE_FOR_LANGUAGE: ur-IN (policy=ask_hi_en, fallback=en-IN)`.
3. Fallback policy A (configurable `TTS_FALLBACK_POLICY`, default
   `ask_hi_en`): the caller is asked deterministically — "I understand
   you, but I cannot speak \<Language\> clearly in this prototype yet.
   Shall we continue in Hindi or English?" — spoken in the configured
   fallback voice (`TTS_FALLBACK_LANGUAGE=en-IN`). Their short answer
   ("Hindi" / "English") is detected and the call continues in that
   language with its Bulbul voice.
4. Policy B (secondary TTS provider) is reserved for later
   (`TTS_FALLBACK_POLICY=secondary_later`) — not implemented, and
   nothing is silently synthesized in the wrong language.

## 7. Code-Mixed Speech

Hinglish and Tanglish stay supported; natural code-switching in other
Indian languages is preserved end to end: STT transcripts are kept as
detected (mixed scripts/words intact, never normalized to a pure
language), the LLM is instructed to keep the caller's natural mix, and
a code-mixed English-detected turn inside a requested language keeps
the requested reply language. Live evidence: Call B (Hinglish turn
after a Hindi request — see §9).

## 8. Per-Call Session State

Each Exotel call gets fresh `detected_language` / `requested_language` /
`reply_language` / `tts_language`; the call log records all four plus a
per-turn `tts_language`. Automated per-call-isolation test proves no
leak between concurrent sessions; the sequential-calls live checks show
each new call starting in English regardless of the previous call.

## 9. Multilingual Live Results (real Sarvam, simulated Exotel calls)

```bash
python prototype/phase4_1_multilingual_live_check.py
# → MULTILINGUAL LIVE CHECK: PASS (40/40 assertions, 2026-09-22)
```

Call A — one call cycling all Bulbul-voiced languages. Each language got an
English switch request, then a native-language sentence (real Bulbul-synthesized
audio fixtures). English is the default lane (covered by every other check).

| Language | Switch request | LLM reply language | TTS voice | STT auto-detect |
|---|---|---|---|---|
| English (en-IN) | ✓ (default lane, all checks) | ✓ | ✓ en-IN | ✓ |
| Hindi (hi-IN) | ✓ | ✓ | ✓ hi-IN | ✓ |
| Bengali (bn-IN) | ✓ | ✓ | ✓ bn-IN | ✓ |
| Tamil (ta-IN) | ✓ | ✓ | ✓ ta-IN | ✓ |
| Telugu (te-IN) | ✓ | ✓ | ✓ te-IN | ✓ |
| Kannada (kn-IN) | ✓ | ✓ | ✓ kn-IN | ✓ |
| Malayalam (ml-IN) | ✓ | ✓ | ✓ ml-IN | ✓ |
| Marathi (mr-IN) | ✓ | ✓ | ✓ mr-IN | ✓ |
| Gujarati (gu-IN) | ✓ | ✓ | ✓ gu-IN | ✓ |
| Punjabi (pa-IN) | ✓ | ✓ | ✓ pa-IN | ✓ |
| Odia (od-IN)¹ | ✓ | ✓ | ✓ od-IN | ✓ (saaras returns `or-IN`; normalized) |

Call B — Hindi request → Hinglish code-mixed turn → pure Hindi turn:
reply language stayed **hi-IN** through the mixed turn, all assistant audio
used the hi-IN voice, and the Hinglish transcript was preserved as spoken
(Latin mix intact). PASS (5/5).

Call C — Urdu request (no Bulbul voice):
`LANGUAGE SWITCH REQUEST: ur-IN` → `TTS_UNAVAILABLE_FOR_LANGUAGE: ur-IN
(policy=ask_hi_en, fallback=en-IN)` → deterministic notice ("I understand
you, but I cannot speak Urdu clearly in this prototype yet. Shall we continue
in Hindi or English?") **spoken in the en-IN voice, never fake-Urdu** →
caller answered "Hindi please" → call continued in **hi-IN with the hi-IN
Bulbul voice** (LLM answer: "मैं अभी आपके account की details नहीं देख पा
रहा हूँ।…"). PASS (5/5). Call-log hygiene: `requested_language=ur-IN`,
`detected_language` preserved, per-turn `tts_language` recorded.

¹ Odia note: saaras:v4 returns the historical `or-IN` code; it is normalized
to `od-IN` before state/logging, so detection, reply and TTS all agree.

## 10. Real PSTN Results (user-side)

The full §11 matrix (≥11 languages, each with transcription / detected
language / reply language / TTS language / audio quality / end-call) remains
user-side via real Exotel calls.

**First real PSTN call already received and verified (2026-09-22, ~10:49):**
a genuine Exotel Voicebot call (real 33-char Exotel call SID, not a
simulation) ran for ~57 s with 4 user turns:
"Tell me what is Hedura" → brand-corrected answer about Zhatura →
"Can you continue with Telugu?" → `LANGUAGE SWITCH REQUEST: te-IN`, reply
spoken in Telugu with the te-IN voice → "Okay now speak in Kannada." →
`LANGUAGE SWITCH REQUEST: kn-IN`, reply spoken in Kannada with the kn-IN
voice. Call log: `call-f4084070.json` (no caller number, no secrets).
Real-line switching en-IN → te-IN → kn-IN confirmed; per-language audio
quality and a full end-call-by-voice on PSTN are still to be covered by the
remaining matrix calls.

## 11. Automated Test Count

**261 passed, 0 failed** (`python -m pytest prototype/tests/ -q`, 2026-09-22),
mock-only — no API credits. Of these, **79 are new Phase 4.1 tests**
(`prototype/tests/test_phase4_1_multilingual.py`): registry completeness
(23 STT / 11 TTS / 12 unsupported codes), alias & native-script matching,
deterministic switch detection (positive + negative cases), session language
state (auto-detect, en→ta→en, en→bn, en→te, sticky requested language,
per-call isolation), LLM-language instruction, and the unsupported-TTS
fallback (notice voice, pending pickup, log-once).

Regression gate after the Phase 4.1 changes:
`python prototype/phase4_stabilization_live_check.py` →
**STABILIZATION LIVE CHECK: PASS** (voice end-call + WSS close,
English→Tamil switch, barge-in, idempotent cleanup — all green;
the working Phase 4 architecture was not rebuilt).

## 12. Remaining Limitations

- 12 languages are understood but not spoken (Bulbul v3 coverage);
  handled with the honest ask_hi_en fallback — full voice support only
  on the 11 listed in §2.
- Automated native-audio fixtures exist only for the 11 Bulbul
  languages (fixtures are synthesized with Bulbul); STT coverage for
  the other 12 is registry/mapping verified, not audio-fixture verified
  — real PSTN calls for those are optional per §11 (voice answer them
  in Hindi/English via the fallback).
- The real-PSTN matrix (§10) is user-side.
- Phase 5 (knowledge base) not started.

## 13. Ready for Phase 5?

NO — Phase 4.1 PSTN confirmation (your real-call matrix) pending first.
