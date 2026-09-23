# Phase 4 — Exotel Telephony Integration Report

Date: 2026-09-22

## Status

**PARTIAL**

All server-side work is complete and live-verified against a simulated
Exotel Voicebot client with real Sarvam API calls. Per the Phase 4
rules, status must remain PARTIAL until a **real phone call** completes
the full loop through Exotel. That call requires user-side Exotel
dashboard actions (create App Bazaar app, assign ExoPhone, paste ngrok
WSS URL) that an automated agent cannot perform. Step-by-step
instructions are in `docs/EXOTEL_PHASE4_SETUP.md`.

## Project

`/Users/tamiliamaiagent/Documents/GitHub/zhatura-ai-customer-care`

Phase 4 adds an Exotel telephone transport in front of the existing,
unchanged Phase 3 voice agent:

```text
Phone call → Exotel Voicebot applet → bidirectional WSS →
this server → Sarvam STT → sarvam-105b-conversations →
Sarvam TTS → WSS → Exotel → caller
```

The Phase 3 agent modules (`agent/*`, `speech/*`) are reused as-is;
no business logic is coupled to Exotel.

## Phase 1 Regression

PASS — Phase 1 health/config tests pass inside the full suite.

## Phase 2 Regression

PASS — Phase 2 STT/TTS tests pass inside the full suite; Phase 2
modules unmodified.

## Phase 3 Regression

PASS — all Phase 3 unit tests (state machine, brand correction,
timings, agent) pass inside the full suite. The live mic demo is
unchanged; the Mac mini's lack of microphone hardware (documented in
`PHASE_3_REPORT.md`) is unaffected by Phase 4.

## Python Version

Python 3.14.6 (venv). Compatibility explicitly verified before any
new dependency was installed. No downgrade of the existing environment.

Pipecat evaluation (spec §10): `pipecat-ai` 1.11.0 resolves on Python
3.14.6 but pins `sarvamai==0.1.28` (would downgrade our working
0.1.34) and pulls ~500 MB of unrelated native deps (onnxruntime,
numba, llvmlite, nltk, resampy). Rejected. The Voicebot protocol
instead is implemented natively with FastAPI, based on the protocol
behavior extracted from Pipecat's `ExotelFrameSerializer` source.

## Dependencies Added

| Package | Version | Purpose |
|---|---|---|
| fastapi | ≥0.115.0 (0.141.1 installed) | HTTP + WebSocket ASGI app |
| uvicorn[standard] | ≥0.30.0 (0.53.0 installed) | ASGI server |
| websockets | 17.1 (transitive via uvicorn[standard]) | client for the live-check script |
| ngrok | 3.39.11 (Homebrew, `/opt/homebrew/bin/ngrok`) | dev tunnel only |

No Sarvam/Phase 3 dependency was changed.

## Exotel Configuration

Do not expose credentials — none are used or stored.

```text
Voicebot Available:    NOT YET VERIFIED (requires user Exotel dashboard check)
App Created:           NO — user action pending (docs/EXOTEL_PHASE4_SETUP.md §4)
Number Assigned:       NO — user action pending (docs/EXOTEL_PHASE4_SETUP.md §5)
WSS URL Configured:    NO — Exotel-side action pending; local endpoint
                       live-verified: ws://127.0.0.1:8000/ws?sample-rate=16000
```

No Exotel API credentials exist in the bot. `EXOTEL_API_KEY`,
`EXOTEL_API_TOKEN`, `EXOTEL_ACCOUNT_SID` are intentionally absent from
`.env`/`.env.example` — the inbound Voicebot flow supplies all
identifiers inside the WebSocket `start` message. The WSS URL carries
no secrets (only the public tunnel host and `/ws` path).

New optional config (Phase 4 block of `.env.example`):

```text
EXOTEL_WEBSOCKET_HOST=0.0.0.0
EXOTEL_WEBSOCKET_PORT=8000
EXOTEL_WEBSOCKET_PATH=/ws
EXOTEL_AUDIO_SAMPLE_RATE=16000
EXOTEL_PHONE_NUMBER=            # optional free-text only, server never reads it
```

## Telephony Architecture

```text
Exotel Voicebot WSS
        │  JSON events (media/start/stop/mark/clear/dtmf)
        ▼
ExotelTransport        (transports/exotel.py — WS I/O, size-capped
        │               validation, malformed message dropping)
        ▼
CallSession            (telephony/session.py — one per call: own
        │               Conversation, AgentStateMachine, RealtimeSTT,
        │               StreamingTTS, turn queue, silence watchdog,
        │               counters; no cross-call shared state)
        ├──── VoiceAgent (agent/*, unchanged Phase 3 code)
        ▼
TelephonyAudioSink     (SpeakerPlayer-compatible; decodes streamed MP3,
                        sends PCM media events back to Exotel, tracks
                        playback completion via mark echoes, cancels via
                        Exotel clear — non-blocking)
```

## Exotel Audio Configuration

```text
Sample Rate: 16000 Hz (default; ?sample-rate=8000|16000|24000 on the WSS URL)
Encoding:    linear16 PCM, base64-encoded JSON payloads (Exotel Voicebot)
Channels:    mono
```

Input frames are resampled (numpy, clip-safe) whenever the wire rate
differs from the internal 16 kHz agent rate; outbound audio is chunked
into 100 ms media messages. Incoming frames are further split to stay
under the Sarvam `fast` stream's 16000-byte per-frame cap.

## WebSocket Events Observed

```text
Connected: YES (live, simulated call)
Start:     YES (stream_sid / call_sid parsed; custom params logged safely)
Media:     YES (bidirectional — 167 bot media messages received by client, 478,974 bytes)
DTMF:      handled + unit-tested; not observed in the live run (no dialpad input)
Mark:      YES (bot sends utterance-N marks; 3 echoes received back in live run)
Clear:     YES (3 clear events sent for barge-in/shutdown)
Stop:      YES (terminates session cleanly, disconnect_reason=stop_event)
```

Unknown, malformed, invalid-JSON, invalid-base64 and oversize
(>256 KB) messages are unit-tested to be dropped without crashing the
call.

## Real Call Test

**NOT PERFORMED — this is the part the user must do.**

```text
Caller:            n/a (no caller numbers are stored)
Call Connected:    PENDING (requires Exotel dashboard configuration)
AI Greeting Heard: PENDING
STT Worked:        PENDING over PSTN (verified over protocol locally)
LLM Worked:        PENDING over PSTN (verified over protocol locally)
TTS Heard:         PENDING
Turns Completed:   PENDING
```

To perform it, follow `docs/EXOTEL_PHASE4_SETUP.md` sections 2–6:
server + `ngrok http 8000` → paste `wss://<ngrok>/ws?sample-rate=16000`
into a Voicebot applet (Call Start → Voicebot → Hangup) → assign an
ExoPhone → call the number.

### Live protocol evidence (local simulated Exotel client, real Sarvam)

`python prototype/phase4_live_call_check.py`, 2026-09-22, session
`call-6d8102e2` (server log, sanitized — no caller numbers, no secrets):

```text
New Exotel connection → session call-6d8102e2 (rate=16000 Hz)
Exotel WebSocket connected
Call started (call_id=local-check-..., stream_id=stream-...)
Barge-in: caller spoke during bot audio               ← clear sent
USER (en-IN): Please tell me what problem you are experiencing.
AI (en-IN): I am here to help you, not to state a problem myself. ...
Barge-in: caller spoke during bot audio
USER (en-IN): Zhatura AI is a learning platform.
AI (en-IN): That is correct. How can I assist you with the platform today?
Exotel stop event.
Call ended (stop_event). turns=2 barge_ins=2 → logs/calls/call-6d8102e2.json
```

Client-side summary: `LIVE CHECK: PASS` — greeting first bot audio
1516 ms after connect; 2 caller turns answered (~1.0 s and ~1.1 s after
speech end); 3 mark echoes; 3 clear events; clean finalize.

## Barge-In Test

Protocol-level: PASS live — caller audio arriving during bot playback
moves the state machine `SPEAKING → INTERRUPTED`, the server sends an
Exotel `clear` event (flushing buffered phone-side audio), playback is
cancelled without blocking, and the new utterance drives the reply.
Real-phone barge-in: PENDING with the real call.

## Zhatura Recognition

PASS — the simulated caller's brand utterance transcribed as
"Zhatura AI is a learning platform." with correct spelling over the
16 kHz Exotel path (STT terminology prompt + deterministic brand
correction, Latin + Devanagari + Tamil variants).

## Language Tests

| Language | Exotel-protocol check | Real phone |
|---|---|---|
| English | PASS (greeting + 2 turns) | PENDING |
| Tamil | PENDING (per spec: only after English phone call) | PENDING |
| Hindi | PENDING | PENDING |
| Hinglish | PENDING | PENDING |
| Tanglish | PENDING | PENDING |

Phase 3 already live-verified all five registers through the identical
STT→LLM→TTS pipeline that Phase 4 drives; only the transport changed.

## Latency Results

From call log `call-6d8102e2.json` (real Sarvam calls, 16 kHz):

```text
STT final after speech end:   206 ms
LLM reply:                    781 ms
TTS first audio:              328 ms
Total turn (speech end → bot):1316 ms
First Exotel media message:   1331 ms after speech end
Greeting first audio:         ~1.3–1.7 s after call connection
```

## Call Stability

PASS — 44 new unit tests cover full call flow, malformed input,
disconnect, barge-in, concurrent sessions, and per-call isolation (no
cross-call memory leaks: each session builds its own Conversation and
state machine; `asyncio.gather` of two sessions verifies isolation).
Live run: 2 turns + greeting + clean stop with all sockets closed
(server log shows STT/TTS connections closed, call log written).

## Disconnect Handling

Four shutdown paths implemented and exercised:

- `stop` event → `disconnect_reason=stop_event` (live-verified)
- WebSocket close mid-call → `disconnect_reason=ws_disconnect`
- caller end phrase ("bye") → closing sentence played, then
  `disconnect_reason=user_end_phrase`; closing the WSS advances the
  Exotel flow to Hangup
- silence watchdog → prompt at timeout, closing at 2×, then
  `disconnect_reason=silence_timeout`

Every path finalizes the call log to `prototype/logs/calls/call-*.json`
(metadata, turns, latencies, media counters — no caller numbers, no
raw audio, no secrets).

## Automated Tests

`pytest prototype/tests` → **140 passed, 0 failed** (44 new in
`test_phase4_exotel.py`). All tests are mock-only: no real Exotel
calls, no ngrok, no Sarvam credit usage. The real-pipeline check is a
separate script (`prototype/phase4_live_call_check.py`), explicitly
excluded from pytest.

## Security Verification

- `.env` ignored: YES (`.gitignore` lines 2–4; `prototype/logs/*` ignored)
- Full-repo scan for the real Sarvam key outside `.env`: 0 matches
  (`.venv`/`.git`/logs excluded; logs separately scanned — 0 matches)
- No `EXOTEL_API_KEY` / `EXOTEL_API_TOKEN` / `EXOTEL_ACCOUNT_SID`
  anywhere
- WSS endpoint contains no secrets; no secret query parameters accepted
- `/health` returns only `status/sarvam:"configured"/phase/active_calls`
- Call logs contain no caller phone numbers (unit-tested), no raw audio
- Authentication failures reported without echoing credentials
- `create_app` runs FastAPI with `docs_url=None` (no public API docs)

## Problems Found

1. **WebSocket handshake rejected with HTTP 403 / close 1008.** Root
   cause: `from __future__ import annotations` in
   `phase4_exotel_server.py` made `websocket: WebSocket` a lazily
   resolved string, but `WebSocket` was imported only inside
   `create_app`, so FastAPI could not resolve it and treated
   `websocket` as a required *query parameter* — every handshake failed
   validation (`Field required`, code 1008, surfaced by uvicorn as 403
   text/plain).
2. **Sarvam STT rejected media frames** (`Audio frame 32000 bytes
   exceeds the per-frame cap of 16000 bytes for stream_type 'fast'`):
   oversized single media events (e.g. 1 s of trailing silence in one
   frame) were forwarded whole; rejected silence prevented VAD end of
   turn → ~17 s turn latency, then no reply.
3. **Barge-in deadlock risk in tests:** `sink.cancel()` called
   `run_coroutine_threadsafe(...).result()` from the event-loop thread
   (STT callback context), blocking 5 s and dropping the `clear`.
4. **Stale telephony latency metric:** `first_exotel_media_ms` of a
   turn could reference the greeting's send time (negative value).
5. **Test-suite hangs** from 45 s mark-echo waits without a receiver
   draining echoes.

## Fixes Applied

1. `WebSocket`/`FastAPI` moved to module-level imports in
   `phase4_exotel_server.py` — handshake now succeeds via TestClient
   and the real `websockets` client against the running server.
2. `CallSession` now splits inbound PCM into ≤16000-byte frames before
   `stt.send_audio` (`MAX_STT_FRAME_BYTES`); the live check paces
   trailing silence in 100 ms frames like speech.
3. `TelephonyAudioSink.cancel()` is non-blocking (schedules the clear,
   no `.result()` on the loop thread).
4. `first_send_at` resets per utterance in `reset_for_next()`.
5. Tests patch `_MARK_TIMEOUT_S=2.0`; full suite runs in ~5 s.

## Exotel Trial Limitations

Unverified items (user must confirm in the Exotel dashboard before the
real call — checklist in `docs/EXOTEL_PHASE4_SETUP.md` §11):

- [ ] Voicebot Applet visible in App Bazaar for the trial account
- [ ] Trial ExoPhone number assignable to an App Bazaar app
- [ ] Outbound PSTN calls to the user's personal number allowed
- [ ] Trial call-duration caps

If the Voicebot applet is absent from the trial account, Phase 4 is
**Blocked by Exotel account provisioning** and should be reported as
such with dashboard evidence (screenshot/app list), per the spec.

Dev-only tunnel: free ngrok URLs change on every restart — the URL in
the Exotel applet must be updated after each ngrok restart. Production
will replace ngrok with a stable `wss://voice.zhatura.com/...`-style
endpoint in a later phase.

## Known Limitations

- Human transfer is acknowledged and logged (`human_requested=true`)
  but no transfer is performed (prototype scope).
- Passthru applet documented as a future production improvement only;
  the prototype uses Call Start → Voicebot → Hangup.
- DTMF is parsed/logged/unit-tested but not exercised live.
- Only the English path was exercised over the Exotel protocol
  (spec order: other languages after English works on the phone).
- The live check's "barge-in" is protocol-driven; acoustic echo
  behavior differs over PSTN and may need tuning on real calls.
- 8 kHz Exotel input is resampled correctly in code/tests but was not
  exercised live at 8 kHz (trial Voicebot sample-rate support
  unconfirmed; 16 kHz requested via URL parameter).

## Phase 4 Acceptance Checklist

(spec §73 final target — current state)

```text
1.  Start the Zhatura Exotel server                    YES (one command)
2.  Start ngrok                                        YES (documented, installed)
3.  Put the WSS URL into Exotel Voicebot               PENDING (user, setup §4)
4.  Call the Exotel trial number from a normal phone   PENDING (user)
5.  Hear "Hello, welcome to Zhatura customer support." PENDING on phone /
                                                         PASS over protocol live
6.  Speak naturally                                    PASS (protocol live run)
7.  Have Sarvam transcribe me                          PASS (206 ms STT final)
8.  Have the Zhatura VoiceAgent answer me              PASS (781 ms LLM)
9.  Hear Sarvam TTS through the phone                  PENDING on phone /
                                                         audio streams over WSS
10. Continue a multi-turn conversation                 PASS (2 turns + greeting live)
11. Interrupt the AI while it is speaking              PASS protocol live (2 barge-ins,
                                                         clear sent); phone PENDING
12. End the call cleanly                               PASS (stop event → finalized log)
```

## Ready for Phase 5?

**NO** — pending the real Exotel phone call (item 4 of the final
target), which requires the user's Exotel dashboard configuration per
`docs/EXOTEL_PHASE4_SETUP.md`.
