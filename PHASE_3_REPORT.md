# Phase 3 Implementation Report

## Status

PASS (live, WAV-driven) — one caveat noted honestly below:
the physical conversation (a human speaking into the Mac microphone
and hearing the speaker) was verified machine-side end to end with
WAV-driven live runs covering the identical code path, but I could not
operate the microphone myself; an interactive human voice session was
not performed by me. Everything except the acoustic mic/speaker round
trip itself was exercised live against the real Sarvam API.

## Phase 1 + Phase 2 Regression Check

PASS — `prototype/app.py` reports `Sarvam API: CONNECTED`,
`STATUS: HEALTHY` (exit 0). Full pytest suite: **96 passed / 0 failed**
(includes all 43 Phase 1 tests and the Phase 2 tests, all mock-only —
no API credits consumed by pytest).

## Sarvam SDK Version

sarvamai 0.1.34 (official SDK; `api-subscription-key` auth)

## Component Configuration

### Realtime STT (microphone / WAV feed → text)

Model: saaras:v4
stream_type: fast
Language: auto-detection (`language_code="auto"`)
Audio: linear16 PCM, 16000 Hz, 100 ms chunks
Endpointing: server-side VAD (threshold 0.3, silence 500 ms,
min speech 250 ms)
**Zhatura terminology prompt: included in EVERY realtime session**
(prompt sent at connect time from `SARVAM_STT_PROMPT`). Auto-reconnect
on disconnect, max 3 attempts with exponential backoff. No raw audio is
logged; transcripts only.

### Conversational LLM

Model: sarvam-105b-conversations (Chat Completion V1, official SDK)
max_tokens: 150, temperature 0.4
System prompt: `prototype/prompts/zhatura_customer_support.md`
(short 1–4 sentence spoken-style customer-support replies; explicitly
no account access, OTP, payments, tickets, or human transfer yet)
Multi-turn memory: full conversation history per session
(`agent/conversation.py`, trimmed at 20 turns). A per-turn system
message carries the STT-detected language so replies match the user's
language.

### Streaming TTS

Model: bulbul:v3, speaker shreya, 22050 Hz MP3 chunks over one
persistent WebSocket (`send_completion_event=true`). Each chunk is
independently decodable (PyAV) and played progressively via sounddevice
— audio starts before the full reply is synthesized.

### Speaker playback / barge-in

`SpeakerPlayer` keeps ONE persistent output stream; `cancel()`
(barge-in) discards queued audio instantly without touching the
stream; `close()` runs only at shutdown (fixes macOS AUHAL err='-50'
churn from per-utterance open/close).

## State Machine

`IDLE → LISTENING → PROCESSING → SPEAKING → LISTENING`, with
`SPEAKING → INTERRUPTED → LISTENING` on barge-in, plus `STOPPING` and
`ERROR`. All transitions validated and logged
(`prototype/agent/state.py`). During development the demo originally
stayed in PROCESSING while speaking, which made barge-in unreachable —
fixed by entering SPEAKING around TTS playback; barge-in then verified
live (see below).

## Live Verification (real Sarvam API calls, 2026-09-21)

Mode: `--selftest` / `--wavs` — generated sample WAVs streamed into the
realtime STT socket at real-time pacing through the production code
path (the only substitution is the audio source).

### English 5-turn session (`--selftest`)

Greeting spoken → 4 user turns answered (one greeting echo correctly
suppressed). Transcript: `prototype/logs/conversations/local-9f3556e4.json`.
Measured latencies (ms, real values per turn):

| STT final | LLM | TTS first audio | Total response |
|-----------|-----|-----------------|----------------|
| 241 | 768 | 308 | 1317 |
| 221 | 396 | 303 | 1629 |
| 209 | 363 | 300 | 1187 |
| 228 | 376 | 310 | 914 |

### Brand recognition ("Zhatura") — realtime

Live findings: the saaras:v4 realtime `prompt` parameter does NOT
reliably fix brand recognition (tested comma-list / sentence / spelled
prompts; also saaras:v3-realtime — 0/3 formats fixed it; batch keyterms
in Phase 2 fixed 7/7). Observed realtime mishearings: Jhatura, Jathura,
Jatura, Jatoora, Zapura, Dhrutura (partials) and, in Indic scripts,
जतुरा / झतूरा / जंतुरा (Hindi), ஜெத்துரா / ஜத்துரா / ஜாத்துரா /
ஜதுரா (Tamil).

Solution shipped: the terminology prompt is still sent with every
session (hard requirement) PLUS a deterministic correction layer
(`agent/brand_correction.py`) rewrites known mishearings to exactly
"Zhatura" on final transcripts before they reach the LLM. Verified
live: e.g. "I can help you check your childs **Zhatura** account.",
"**Zhatura** AI is a learning platform." in final transcripts;
correction hits are logged.

### Barge-in / interruption

Verified live in the selftest session: user audio arriving while the AI
spoke produced `SPEAKING → INTERRUPTED`, instant playback cancellation
("Playback cancelled (barge-in)"), then `INTERRUPTED → LISTENING` and
the interrupting turn was answered next. Three separate barge-in cycles
in one session (`/tmp`-captured log; states in transcript session logs).
Turns are serialized through a queue — replies never overlap.

### Silence handling

~20 s idle (config: `CONVERSATION_SILENCE_TIMEOUT_SECONDS`) →
"Are you still there?" spoken; continued silence → polite closing and
clean shutdown. Observed live at the tail of a selftest run.

### Multilingual live runs

All five sample languages driven through the full pipeline with
auto-detected language and same-language spoken replies:

- **Tamil** — detected ta-IN; Tamil LLM replies; Tamil TTS.
  Transcript: `local-5c92d017.json` (totals 1350/999/899 ms).
- **Hindi** — detected hi-IN; Hindi replies + TTS.
  Transcript: `local-0bbc3ddf.json` (totals 1343/1004/1002 ms).
- **Hinglish** — detected hi-IN (code-mixed Devanagari+Latin handled);
  Hinglish-style replies. Transcript: `local-9a957cad.json`.
- **Tanglish** — detected ta-IN; Tanglish-style replies.
  Same transcript file (combined run).

Observed end-to-end total response latency across all live turns:
**~0.9–1.8 s** (STT final 203–482 ms, LLM 335–1030 ms, TTS first audio
300–402 ms). Total includes turn-queue wait when utterances arrive
back-to-back; per-stage numbers are per-turn real measurements, printed
after every turn and stored in `logs/conversations/local-*.json`.

### Clean shutdown

Ctrl+C / end phrase / silence timeout all route through one shutdown
path: turn worker + silence watchdog cancelled and awaited, mic stopped,
speaker stream closed, both Sarvam WebSockets closed, transcript JSON
saved. Verified in every live run ("Session ended.", no hanging tasks).

## pytest Results

96 passed / 0 failed (`pytest prototype/tests -q`).
All tests mock Sarvam and audio hardware; zero API credits consumed.
Coverage includes: conversation memory, state-machine transitions,
brand correction (Latin + Devanagari + Tamil variants), echo
suppression, realtime STT event dispatch + required connect parameters
(prompt/keyterms, VAD, encoding, sample rate, auto language), chat
language hint, ending phrases, TTS language mapping, player
cancel/reset semantics, latency math.

## Security Confirmation

- `.env` is git-ignored (`git check-ignore -v .env` → matched).
- Full-repo scan for the API key: **clean** — key exists only in `.env`;
  not in logs, transcripts, reports, or source.
- WebSocket/LLM error paths redact to exception type names / status
  codes; no headers or payloads logged.
- `prototype/logs/` (including conversation transcripts) is git-ignored.
- `.env.example` contains placeholders only.

## Known Limitations / Risks

- Echo protection is a word-overlap heuristic; without headphones the
  mic can hear the speaker. The greeting echo was correctly suppressed
  live, but long AI replies heard by the mic could still generate
  spurious user turns — use headphones for clean interactive sessions.
- Physical mic/speaker interactive session was not performed by me
  (no human operator). On 2026-09-22 the mic path was attempted live and
  the machine reported **no input device at all** (`sd.query_devices()`
  shows only "Mac mini Speakers, 0 in / 2 out") — this Mac mini has no
  microphone hardware attached, so an interactive voice session requires
  connecting an external mic (USB mic / headset / AirPods). The demo's
  pre-check was updated to detect this case explicitly and say so
  (previously it printed only the permission hint, which would have been
  misleading). With a mic connected, macOS will prompt for permission on
  first run, then the same verified code path runs.
- Realtime brand recognition still relies on the deterministic
  correction layer; novel mishearings outside the variant list will
  pass through uncorrected.
- The LLM occasionally answers the *content* of sample sentences
  literally (expected — sample WAVs contain support-agent lines).

## Out of Scope (enforced)

No Exotel, no telephony WebSocket, no real customer tools (no OTP,
payments, tickets), no RAG, no human telephone transfer, no CRM, no
production hosting. Human-transfer asks are politely acknowledged as a
future capability.

## Next Recommended Step

Phase 4: Exotel Voicebot/WebSocket telephony integration — replace the
local mic/speaker transport with Exotel's call audio stream on top of
this orchestrator (`VoiceAgent` is transport-agnostic by design), then
add Zhatura account tools behind authentication.
