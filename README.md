# Zhatura AI Customer Care

AI-powered voice customer-service system for Zhatura, built on
Exotel (telephony), Sarvam AI (speech/AI), Zhatura knowledge, and
Zhatura customer-service tools, with human-agent escalation.

## Project Purpose

Provide automated, voice-first customer care for Zhatura customers:
answer calls, understand spoken requests (Indian languages included),
resolve them against Zhatura knowledge and customer-service APIs, and
escalate to a human agent when needed.

## Current Status

**Phase 2 — Sarvam Speech Prototype**

Working: project foundation, configuration, health checks, Sarvam TTS
(`bulbul:v3`, WAV output), Sarvam STT (`saaras:v4`, mode `transcribe`),
a reusable multilingual audio sample set, a TTS→STT round-trip demo,
and keyterm-assisted brand recognition.

> **Exotel integration begins in a later phase.**
> **Voice calls / realtime conversation are not implemented yet.**

## Phase 2 — Sarvam Speech Prototype

### Generate TTS audio

```bash
python -m prototype.speech.tts \
  --text "Hello, welcome to Zhatura customer support." \
  --output audio_samples/sarvam/english/welcome.wav
```

Options: `--language en-IN|ta-IN|hi-IN|...`, `--speaker shreya|...`
(Bulbul v3 voices; default speaker `shreya`, 24000 Hz WAV).

### Transcribe audio (STT)

```bash
python -m prototype.speech.stt \
  --input audio_samples/sarvam/english/welcome.wav

# with brand keyterm assistance (recommended — see below)
python -m prototype.speech.stt \
  --input audio_samples/sarvam/terminology/brand_zhatura.wav \
  --keyterms "Zhatura,Zhatura AI,AI Chess Coach,Chess Academy"
```

### Regenerate the sample set

```bash
python prototype/generate_samples.py          # skips existing files
python prototype/generate_samples.py --force  # regenerates all
```

### Live TTS → STT round-trip demo

```bash
python prototype/phase2_demo.py
```

Prints the original text, generated audio path, transcript (with and
without Zhatura keyterms), and a PASS/FAIL verdict.

### Optional microphone recording

```bash
python -m prototype.speech.microphone --output audio_samples/input/clip.wav --seconds 5
```

Requires `sounddevice` (in requirements.txt) and macOS microphone
permission for your terminal.

### Test languages

English (en-IN), Tamil (ta-IN), Hindi (hi-IN), Hinglish, Tanglish —
definitions in `audio_samples/sentences.md`.

### Output folders

```text
audio_samples/sarvam/<language>/*.wav   # generated TTS samples
audio_samples/input/                    # microphone / user-provided input
audio_samples/transcripts/              # saved STT results (JSON)
```

### Important finding — brand keyterms

Without keyterms, Sarvam STT never transcribes "Zhatura" correctly
(Jhatura / Jatura / Jathura / …). With the `keyterms` parameter, all 7
brand samples are exact. **Later phases must pass Zhatura keyterms on
every STT call.** Details: `audio_samples/evaluation.md`.

### Current limitations

- WAV input/output only (STT tested with 24000 Hz WAV from bulbul:v3).
- No realtime streaming STT (Phase 3+).
- Hinglish/Tanglish STT returns native-script transcripts
  (Devanagari/Tamil), which is expected STT behavior.
- TTS voice quality needs a human listening review
  (`audio_samples/evaluation.md`).

## Requirements

- Python 3.9 or newer (developed/verified on Python 3.14.6)
- A Sarvam AI API subscription key

## Setup

```bash
cd zhatura-ai-customer-care
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Configuration

Copy the example file and add your real key:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
SARVAM_API_KEY=your_real_key_here
```

**Never commit `.env`.** It is excluded via `.gitignore`.

## Run Health Check

```bash
python prototype/app.py
```

This performs local checks (Python version, `.env`, configuration,
Sarvam client initialization) and one minimal live Sarvam API call to
confirm the key authenticates. Expected output ends with:

```text
Sarvam API:         CONNECTED
Overall Status: HEALTHY
STATUS: HEALTHY
```

Exit code `0` = healthy, `1` = unhealthy (errors printed, never
containing secrets).

## Run Tests

```bash
python -m pytest prototype/tests/ -v
```

Unit tests mock all external Sarvam calls and do **not** consume
Sarvam API credits. Live checks (`prototype/app.py`,
`prototype/phase2_demo.py`, `prototype/generate_samples.py`) run only
when invoked explicitly.

## Project Structure

```text
zhatura-ai-customer-care/
├── prototype/
│   ├── agent/          # conversational agent (later phase)
│   ├── speech/         # Phase 2: Sarvam TTS/STT modules
│   │   ├── tts.py          # bulbul:v3 text-to-speech → WAV
│   │   ├── stt.py          # saaras:v4 speech-to-text (WAV in)
│   │   ├── audio_utils.py  # file validation / WAV metadata
│   │   └── microphone.py   # optional local recording helper
│   ├── telephony/      # Exotel integration (later phase)
│   ├── knowledge/      # Zhatura knowledge/RAG (later phase)
│   ├── tools/          # Zhatura customer-service tools (later phase)
│   ├── prompts/        # agent prompts (later phase)
│   ├── logs/           # application logs (git-ignored)
│   ├── tests/          # unit tests (mocked; no API credits)
│   ├── config.py       # .env loading + validation
│   ├── sarvam_client.py# official Sarvam SDK client factory
│   ├── health.py       # Phase 1 health checks
│   ├── app.py          # Phase 1 entry point
│   ├── generate_samples.py  # live TTS sample-set generator
│   ├── phase2_demo.py  # live TTS→STT round-trip demo
│   ├── agent/          # state machine, conversation, voice agent, brand fix
│   └── phase3_voice_demo.py  # LIVE local voice agent (mic ↔ speaker)
├── audio_samples/      # sentences.md, sarvam/ samples, evaluation.md
├── docs/               # master project plan
├── .env                # secrets (git-ignored — never commit)
├── .env.example        # placeholder template
├── requirements.txt
└── README.md
```

## Phase 3 — Live Conversational Voice Agent (local)

A full-duplex local voice agent:
Mac **microphone → Sarvam realtime STT → Sarvam chat LLM →
Sarvam streaming TTS → Mac speaker**, with barge-in support.

Run it (live, uses real API credits and your mic/speaker):

```bash
python prototype/phase3_voice_demo.py
```

Automated live verification without a microphone (streams generated
WAV samples through the realtime pipeline):

```bash
python prototype/phase3_voice_demo.py --selftest
python prototype/phase3_voice_demo.py --wavs audio_samples/sarvam/tamil/*.wav
```

### macOS microphone permission

On first run macOS asks to allow microphone access for your terminal
app. If blocked: **System Settings → Privacy & Security → Microphone**,
enable your terminal, then re-run. The demo pre-checks the mic and
prints this hint if permission is missing.

### Architecture

| Stage | Component | Setting |
|-------|-----------|---------|
| Capture | `speech/microphone.py` (sounddevice) | 16 kHz mono linear16 |
| STT | `speech/realtime_stt.py` | saaras:v4, stream_type=fast, endpointing=VAD, language auto |
| Brand fix | `agent/brand_correction.py` | deterministic correction of known "Zhatura" mishearings |
| Brain | `agent/voice_agent.py` | sarvam-105b-conversations, 1–4 sentence spoken-style replies, multi-turn memory |
| TTS | `speech/streaming_tts.py` | bulbul:v3 speaker shreya, streaming MP3 → progressive playback |
| Orchestration | `phase3_voice_demo.py` | state machine + turn queue + silence watchdog |

**Every realtime STT session carries the Zhatura terminology prompt**
(`SARVAM_STT_PROMPT` in `.env`) — this is a hard requirement; a
deterministic brand-correction layer additionally fixes observed
mishearings (Latin + Devanagari + Tamil scripts) on final transcripts,
because live testing showed the realtime `prompt` parameter alone does
not fix brand recognition.

### Features

- Partial + final transcripts printed live; finals drive the agent.
- Replies in the user's language (English, Tamil, Hindi, Hinglish,
  Tanglish all live-verified 2026-09-21).
- **Barge-in:** user speech during AI playback cancels audio instantly
  (`SPEAKING → INTERRUPTED → LISTENING`); turns are serialized through
  a queue so replies never overlap.
- Silence handling: ~20 s idle → "Are you still there?"; continued
  silence → polite closing + shutdown.
- Echo protection: transcripts that match the agent's own current
  utterance are suppressed (heuristic; headphones recommended).
- Measured per-turn latencies (real values) printed per turn and stored
  in `logs/conversations/local-*.json`.
- End phrases ("bye", "that's all", …) close politely; Ctrl+C shuts
  down cleanly, closing mic, speaker, and both Sarvam WebSockets.

### Phase 3 scope limits (by design)

No Exotel, no telephony WebSocket, no real customer-account tools,
no OTP/payments/tickets, no RAG, no human telephone transfer, no CRM,
no production hosting. Human-transfer requests are acknowledged but
explained as a later-phase capability.

## Phase 4 — Exotel Telephony Voice Service

The same Phase 3 agent, fronted by an Exotel-compatible telephony
WebSocket instead of Mac mic/speaker:

```text
Phone call → Exotel Voicebot applet → WSS → this server → Sarvam → caller
```

```bash
python prototype/phase4_exotel_server.py     # terminal 1
ngrok http 8000                              # terminal 2 (dev tunnel)
python prototype/phase4_live_call_check.py   # local full-loop check
```

- Voicebot-Applet protocol implemented natively (linear16 PCM/base64
  media, `connected`/`start`/`media`/`dtmf`/`mark`/`clear`/`stop`);
  Pipecat was evaluated and rejected — it would pin `sarvamai` back to
  0.1.28 and add ~500 MB of unrelated dependencies.
- **Paced outbound audio**: TTS PCM is buffered and sent as fixed
  100 ms frames at real-time cadence (stabilization fix — un-paced
  bursts caused choppy PSTN audio); per-utterance `TTS OUT` metrics are
  logged (rate, frame size, chunks, buffer depth).
- **Dynamic language switching**: explicit caller requests ("speak
  Tamil", "Hindi mein baat karo", "தமிழில் பேச முடியுமா?") are detected
  deterministically and drive the LLM reply language and TTS language
  (en-IN/ta-IN/hi-IN); code-mixed Hinglish/Tanglish are supported.
- **Deterministic end-call intent**: "cut the call", "end the call",
  "hang up", "call cut pannunga", etc. → closing message → bot closes
  the WebSocket → Exotel advances to the Hangup applet.
- **Idempotent per-call cleanup**: every disconnect path (caller hangup,
  Exotel stop, bot end-call, silence timeout, network drop) converges on
  one cleanup; duplicate `stream_sid` reconnects shut down the stale
  session; `GET /health.active_calls` returns to 0 after each call.
- Per-call isolated sessions: each WebSocket connection gets its own
  conversation, state machine, STT/TTS streams and call log; no
  cross-call memory leaks.
- Telephony barge-in via Exotel `clear` events; playback completion
  tracked with `mark` echoes.
- `/health` exposes only safe data (`{"status","sarvam":"configured",
  "phase","active_calls"}`).
- Malformed/oversize WebSocket messages are validated and dropped, never
  crash a call; call logs in `prototype/logs/calls/` hold no caller
  numbers, no secrets, no raw audio.
- No Exotel API credentials required for the inbound Voicebot flow.

Local stabilization verification (real Sarvam, simulated Exotel —
3 sequential calls: voice end-call, English→Tamil switch, barge-in):

```bash
python prototype/phase4_stabilization_live_check.py
```

### Phase 4.1 — full Sarvam multilingual coverage

- All **23 scheduled Sarvam STT languages** handled with
  `language_code="auto"` (English, Hindi, Bengali, Tamil, Telugu,
  Kannada, Malayalam, Marathi, Gujarati, Punjabi, Odia + Assamese, Urdu,
  Nepali, Konkani, Kashmiri, Sindhi, Sanskrit, Santali, Manipuri, Bodo,
  Maithili, Dogri); the detected language is stored per call
  (`detected_language` / `requested_language` / `reply_language` /
  `tts_language`, never shared between calls).
- **Bullet-proof language registry** in `prototype/agent/languages.py`
  (name, BCP-47 code, STT/TTS capability, native script name, aliases
  like "Tamizh" / "Bangla" / native words) — the single source of truth
  for switching and TTS routing.
- Explicit switch requests work for every language ("Speak Tamil",
  "Can you speak Bengali?", "Please continue in Telugu",
  "Kannada please", "Hindi mein baat karo") with immediate effect.
- **Bulbul v3 TTS supports 11 of them** (en/hi/bn/ta/te/kn/ml/mr/gu/pa/
  od). For the 12 languages without a Bulbul voice, the bot never fakes
  the language: `supports_tts()` routes to a configurable fallback
  policy (`TTS_FALLBACK_POLICY=ask_hi_en` asks the caller whether to
  continue in Hindi or English, spoken in the fallback voice), and logs
  `TTS_UNAVAILABLE_FOR_LANGUAGE: <code>`.
- Code-mixed speech (Hinglish/Tanglish and natural code-switching in
  other languages) preserved — replies never collapse mixed speech into
  plain English.
- Concise per-call logs: `LANGUAGE DETECTED`, `LANGUAGE SWITCH REQUEST`,
  `REPLY LANGUAGE`, `TTS LANGUAGE`, `TTS_UNAVAILABLE_FOR_LANGUAGE`
  (no phone numbers, no secrets).

Multilingual live verification (real Sarvam, simulated Exotel — one call
cycling all 11 spoken languages, one Hinglish call, one Urdu-fallback
call):

```bash
python prototype/phase4_1_multilingual_live_check.py
```

Full setup (App Bazaar flow, ngrok URL, ExoPhone assignment, trial
limitations): **[docs/EXOTEL_PHASE4_SETUP.md](docs/EXOTEL_PHASE4_SETUP.md)**.
Report: [PHASE_4_REPORT.md](PHASE_4_REPORT.md).

## Phase 5/6 — Knowledge Base + Grounded Customer Support

The voice agent answers product questions ONLY from verified Zhatura
knowledge (`prototype/knowledge/sources/*.md`) — and says "I don't have
verified information about that yet" instead of inventing facts.

```text
caller turn → brand correction → topic/audience detect
→ hybrid retrieval (lexical + phrase + topic/audience boosts, in-memory)
→ confidence + honesty guards (unknown / pricing / account-specific)
→ grounded context injected as a system message → LLM answers in the
   caller's language, strictly from the context
```

- **20 verified source files** covering overview, AI Chess Coach,
  student/parent/coach/academy features, lessons/sessions, game
  analysis, progress tracking, puzzles, plans/pricing, account/login
  help, technical support, multilingual support, FAQ, escalation,
  organization plans, privacy/security, supported platforms and common
  issues.
- **Trusted sources only**: every chunk carries source file, section,
  `verified` flag, `source_type` and provenance. Pricing/plan files carry
  `status: unavailable` — the honest answer is grounded and the pricing
  guard can never invent a price, plan name, discount, renewal or trial
  term.
- **Validation**: `python -m knowledge.build_index` checks for empty
  documents, duplicate IDs/content, missing metadata, unverified chunks,
  placeholder text, fixture leaks and unapproved pricing claims.
- **Knowledge gaps**: see [`KNOWLEDGE_GAPS.md`](KNOWLEDGE_GAPS.md).
- **Account-specific safety**: "my child cannot see today's lesson"
  explains general product behaviour only, says clearly the assistant
  cannot see any account, and offers a support next step.
- **Multilingual intact**: retrieval works with native-script and
  code-mixed transcripts (ta/hi/te and more); the LLM replies in the
  caller's language.
- **Latency**: synchronous in-memory retrieval stays well under the
  200–300 ms target.

Add or update knowledge:

```bash
$EDITOR prototype/knowledge/sources/<topic>.md   # keep verified facts only
cd prototype && python -m knowledge.build_index  # validate + rebuild check
# restart the (dev) server process to pick changes up
```

Simulated live verification (dev server on port 8001 — never touches
the production 8000 server):

```bash
EXOTEL_WEBSOCKET_PORT=8001 python prototype/phase4_exotel_server.py   # A
python prototype/phase5_knowledge_live_check.py                       # B
```

Reports:
[PHASE_5_KNOWLEDGE_BASE_REPORT.md](PHASE_5_KNOWLEDGE_BASE_REPORT.md),
[PHASE_6_KNOWLEDGE_EXPANSION_REPORT.md](PHASE_6_KNOWLEDGE_EXPANSION_REPORT.md).

## Security Notes

- The Sarvam API key lives only in `.env` (git-ignored).
- The key is never printed, logged, included in errors, or committed.
- `.env.example` contains a placeholder only.
- Authentication failures (HTTP 401/403) are reported safely as
  "authentication failure" without echoing any credentials.
- Application logs are written to `prototype/logs/` (git-ignored)
  and contain no secrets.

## Development Roadmap

The master plan lives in
[`docs/Zhatura_Exotel_Sarvam_AI_Voice_Service_Project_Plan.md`](docs/Zhatura_Exotel_Sarvam_AI_Voice_Service_Project_Plan.md).

- **Phase 1:** project foundation + Sarvam connectivity proof ✅
- **Phase 2:** Sarvam TTS/STT prototype + audio sample set ✅
- **Phase 3:** local live two-way conversational voice agent ✅
- **Phase 4:** Exotel Voicebot telephony integration — server,
  protocol, barge-in and call logging implemented and live-verified ✅
- **Phase 4.1:** multilingual voice switching (11 Indian languages) ✅
- **Phase 5/6:** verified knowledge base + grounded customer-support
  answers ✅
- Later phases: customer tools (auth/OTP, tickets, payments),
  human-agent escalation, outbound calls, production deployment
# Zhatura-AI-chess-coach-customer-support
# Zhatura-AI-chess-coach-customer-support
