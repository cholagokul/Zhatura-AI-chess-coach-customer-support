# Phase 2 Implementation Report

## Status

PASS

## Phase 1 Regression Check

PASS — `prototype/app.py` reports `Sarvam API: CONNECTED`,
`STATUS: HEALTHY` (exit 0). Two Phase 1 tests broke because the real
`.env` (added after Phase 1) made "missing key" tests see a real key;
fixed by pointing those tests at a nonexistent env file. Full suite:
**43 passed / 0 failed**.

## Sarvam SDK Version

sarvamai 0.1.34 (official SDK; `api-subscription-key` auth)

## TTS Configuration

Model: bulbul:v3
Language: en-IN (default; also ta-IN, hi-IN used)
Speaker: shreya (Bulbul v3 voice, config-overridable, validated against SDK voice list)
Sample Rate: 24000 Hz, 16-bit mono WAV (`output_audio_codec="wav"`,
`enable_preprocessing=True`; v2-only pitch/loudness deliberately not used)

## STT Configuration

Model: saaras:v4
Language: en-IN default; per-sample ta-IN / hi-IN used
Mode: transcribe
Extras: `keyterms` parameter integrated and tested (saaras:v4 supports it in this SDK version)

## Files Created / Modified

Created:
```text
prototype/speech/tts.py
prototype/speech/stt.py
prototype/speech/audio_utils.py
prototype/speech/microphone.py        (optional helper; sounddevice 0.5.6 working)
prototype/generate_samples.py         (live sample-set generator — not in pytest)
prototype/phase2_demo.py              (live TTS→STT round-trip demo — not in pytest)
prototype/tests/test_tts.py
prototype/tests/test_stt.py
prototype/tests/test_audio_utils.py
audio_samples/sentences.md
audio_samples/evaluation.md
audio_samples/sarvam/{english,tamil,hindi,hinglish,tanglish,terminology}/*.wav  (23 files)
audio_samples/transcripts/stt_results.json
PHASE_2_REPORT.md
```

Modified:
```text
prototype/config.py        (+7 Phase 2 speech settings with safe defaults)
prototype/speech/__init__.py
prototype/tests/test_health.py  (isolation fix — see Problems Found)
.env.example               (+ speech settings placeholders)
.env                       (+ speech defaults; key untouched)
requirements.txt           (+ sounddevice, optional microphone helper only)
README.md                  (+ Phase 2 section)
```

## Live TTS Result

PASS — 22 corpus samples + 1 demo sample generated via real Sarvam
API (23/23 succeeded). Every file validated as a readable 24000 Hz
mono WAV via the Python `wave` module; sizes 57 KB–262 KB, durations
1.2–5.5 s.

## Live STT Result

PASS — all 23 generated WAVs transcribed successfully. Transcripts
are non-empty and preserve sentence meaning in en-IN, ta-IN, hi-IN.
Hinglish/Tanglish inputs return native-script transcripts (expected).
Raw results: `audio_samples/transcripts/stt_results.json`.

## TTS → STT Round-Trip Result

PASS — `python prototype/phase2_demo.py`:

```text
Original:   Hello, welcome to Zhatura customer support.
Audio:      audio_samples/sarvam/english/phase2_demo.wav (2.987s, 24 kHz)
Transcript: Hello, welcome to Jhatura customer support.        (no keyterms)
Transcript: Hello, welcome to Zhatura customer support.        (with keyterms)
Verdict:    PASS
```

(Punctuation/brand spelling differences are documented below; neither
affects the round-trip verdict, which checks meaning preservation.)

## Zhatura Brand Recognition Test

**Without keyterms: FAIL (0/7)** — Sarvam never recognizes "Zhatura":
Jhatura, Jatura, Jathura, JATURA, Jatuara, ஜதுரா, जतुरा.

**With keyterms (`["Zhatura","Zhatura AI","AI Chess Coach","Chess Academy", …]`): PASS (7/7)** — exact brand spelling and capitalization
(also fixes "Parent/Coach/Student Dashboard" capitalization).

**Action for Phase 3+:** pass Zhatura keyterms on every STT call.
The STT module already supports this via `keyterms=`.

## Languages Tested

English (en-IN), Tamil (ta-IN), Hindi (hi-IN), Hinglish (hi-IN voice),
Tanglish (ta-IN voice).

## Audio Samples Generated

```text
audio_samples/sarvam/english/      5 samples + phase2_demo.wav
audio_samples/sarvam/tamil/        3 samples
audio_samples/sarvam/hindi/        3 samples
audio_samples/sarvam/hinglish/     2 samples
audio_samples/sarvam/tanglish/     2 samples
audio_samples/sarvam/terminology/  7 brand samples
```

All meaningful filenames (`welcome`, `account_help`, `problem`,
`subscription`, `human_transfer`, `brand_*`); existing files are
skipped on re-run unless `--force`.

## Automated Test Results

**43 passed / 0 failed** (`pytest prototype/tests/ -q`, 0.2 s).

- 12 Phase 1 tests (config/health, mocked)
- 10 TTS tests (validation, mocked success/errors, rate limit,
  write failure, no-key-leakage)
- 12 STT tests (missing/corrupt/unsupported file, mocked
  success/errors, keyterms, no-key-leakage)
- 9 audio-utils tests (directories, validation, metadata, safe naming)

No live Sarvam calls in pytest. Live paths: `prototype/app.py`,
`prototype/phase2_demo.py`, `prototype/generate_samples.py`.

## Security Verification

- `.env` ignored: YES (`git check-ignore .env` matches; absent from `git status`)
- API key hard-coded: NO
- API key in logs (`prototype/logs/app.log`): NO (scanned against real value — clean)
- API key in saved transcripts JSON: NO (scanned — clean)
- `.env.example`: placeholders only
- SDK/httpx logging pinned below headers level; no base64 audio logged

## Problems Found

1. **Phase 1 test isolation:** with a real key now in `.env`, the two
   "missing key" tests loaded it via `load_dotenv` and failed.
2. **Brand misrecognition without keyterms** — documented above;
   materially affects every later phase.
3. Hinglish/Tanglish STT outputs native script (Devanagari/Tamil),
   not Latin — expected behavior, but relevant for transcript display
   in later phases.

## Fixes Applied

1. Tests now point the config loader at a guaranteed-nonexistent env
   file for missing-key cases (`test_health.py`); suite green again.
2. STT module integrates `keyterms` end-to-end (function arg + CLI
   `--keyterms`); demo and evaluation compare with/without.

## Known Limitations

- WAV only for Phase 2 (STT tested with 24 kHz bulbul:v3 output).
- No realtime/streaming STT — Phase 3 (`saaras:v3-realtime` / saaras:v4
  streaming per current Sarvam docs).
- TTS voice quality not human-reviewed; evaluation.md marks
  "Manual listening review required".
- Microphone helper untested with a live recording (sounddevice
  installed and importable; macOS mic permission is a user action).

## Phase 2 Acceptance Checklist

Phase 1
- [x] Phase 1 remains healthy (HEALTHY, exit 0)
- [x] Previous tests still pass (12/12 after isolation fix)

TTS
- [x] Real Sarvam TTS succeeds
- [x] WAV/audio file is created
- [x] File is non-empty (all ≥ 57 KB, valid WAV)
- [x] At least English sample generated (5 + demo)
- [x] Zhatura terminology samples generated (7)

STT
- [x] Real Sarvam STT succeeds
- [x] Generated audio transcribed (23/23)
- [x] Transcript non-empty
- [x] Zhatura terminology recognition evaluated (0/7 plain, 7/7 with keyterms)

Testing
- [x] New automated tests pass (43 total)
- [x] Live test runs separately (phase2_demo.py / generate_samples.py)
- [x] No unnecessary API calls in unit tests

Security
- [x] `.env` ignored
- [x] API key not exposed
- [x] Logs do not contain API key

Documentation
- [x] Audio sample structure exists
- [x] `sentences.md` exists
- [x] `evaluation.md` exists
- [x] README updated
- [x] `PHASE_2_REPORT.md` created

## Ready for Phase 3?

YES

Blocking caveat to carry into Phase 3: **always send Zhatura keyterms
with STT calls.** Human listening review of the sample set is
recommended but non-blocking.
