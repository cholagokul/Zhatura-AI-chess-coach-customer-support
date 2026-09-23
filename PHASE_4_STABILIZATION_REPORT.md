# PHASE 4 STABILIZATION REPORT — Real Exotel Call Fixes

Date: 2026-09-22
Scope: fix only the four issues observed on real PSTN calls after the
Phase 4 base was live-verified. No architecture changes, no Phase 5 work,
no RAG/CRM/OTP/tickets/payments/transfer/outbound/production features.

## 1. Status

**STABILIZED — code-side verification complete (protocol-level PASS);
final PASS still requires your real PSTN re-test.**

- Real PSTN calls connect and converse (verified by you pre-stabilization):
  the full loop works.
- All four reported issues root-caused, fixed, and re-verified locally with
  **real Sarvam** against the **real running server**, in a simulated
  Exotel call flow that faithfully mimics Exotel behavior (echoes `mark`
  events, speaks only when the bot is idle, pace-matched media).
- 3 sequential live calls: **13/13 checks PASS**
  (`prototype/phase4_stabilization_live_check.py` → `STABILIZATION LIVE CHECK: PASS`).
- Full automated suite: **182 passed, 0 failed** (mock-only, no credits).
- Base Phase 4 live check re-run post-changes: **PASS** (no protocol
  regression).

## 2. Issues Reproduced

All four were reproduced and confirmed in automated tests before fixing
(the choppy audio additionally confirmed by a pre-fix server metric, see
§3, root cause 1):

| Issue | Reproduction |
|---|---|
| Choppy/broken bot voice over Exotel | Pre-fix `TTS OUT` metric showed the greeting's ~3.5 s of PCM (`max_buffer=156708B`) delivered in bursts; automated pacing test proved un-paced send. |
| "Can you speak in Tamil?" → "I can only speak in English right now" | LLM decided language behavior alone; deterministic detector test reproduced the wrong outcome; prompt had no switch rule. |
| "Can you cut the call?" did not end the call | `run()` parked on `await transport.receive()`; the end flag never woke it, so the WSS stayed open and the call never reached the Hangup applet. Reproduced live: `END_CALL DETECTED` logged, WSS stayed open. |
| Repeated calls unreliable | Non-idempotent cleanup: shutdown could double-finalize, the parked run-task survived external shutdown, and a duplicate `stream_sid` produced two live sessions (leaked `active_calls`). Reproduced by the duplicate-session test. |

## 3. Root Causes

1. **Choppy audio — un-paced outbound sends.** Sarvam streams TTS MP3
   chunks much faster than real time. The old sink decoded and sent them
   to Exotel immediately, so ~3.5 s of audio hit the telephone playout
   buffer at once, in irregular bursts — heard as choppy/broken voice.
2. **Language refusal — behavior left entirely to the LLM.** Nothing in
   the system prompt governed language switching, and the reply language
   tracked only the STT guess, so an English-phrased switch request got a
   chat-model judgment call (which answered "English only").
3. **Voice end-call ignored — parked receive loop.** End detection set a
   stop flag, but `asyncio` was parked inside `await transport.receive()`;
   the flag was never observed, the session never closed the WebSocket,
   and Exotel never advanced to the Hangup applet.
4. **Repeated-call instability — cleanup gaps.** `shutdown()` was not
   idempotent, an externally-triggered shutdown left the run task parked
   forever (handler never returned, `active_calls` never drained), and a
   duplicate `stream_sid` connection left a stale zombie session.

A fifth, non-product issue surfaced in my own call-flow simulation: it
did not echo `mark` events the way real Exotel does. The server (by
design) waits for the mark echo — bounded at 45 s — before considering
playback complete, so the first stabilization run showed a 45 s hang on
the end-call path purely from the simulation. Simulation fixed (mark
echoes, polite-caller idle waiting, `active_calls==0` as the cleanup
gate); no production change came from this.

## 4. Fixes Applied

1. **Paced outbound audio (fixes issue A).** Decoded TTS PCM now goes
   into a shared byte buffer; a loop-thread pacer task emits **one
   fixed-size media frame per 100 ms at real-time cadence**. Sub-frame
   utterance tail is flushed when the utterance finishes; buffer is
   capped at 15 s; barge-in clears the buffer and sends Exotel `clear`.
   `feed_mp3_chunk` lazily starts the pacer via `call_soon_threadsafe`
   (ordering defense). Decode still runs on worker threads; `finish()`
   remains worker-thread-only — never called on the event loop
   (deadlock class eliminated and documented).
2. **Deterministic language switching (fixes issue B).**
   `detect_language_switch(text)` matches explicit switch requests —
   language name **plus a request verb** ("speak/switch/talk in Tamil",
   "Hindi mein baat karo", "தமிழில் பேச முடியுமா?") — so "I am learning
   Tamil" or "Tamil chess lessons" are NOT switches. Per-call
   `session.language` state; explicit switch wins for that turn, then
   live STT auto-detection follows the caller's actual speech. System
   prompt now includes a Language Switching section: switch immediately,
   never say "I can only speak in English", supported languages
   English/Tamil/Hindi/Hinglish/Tanglish. TTS language follows the reply
   language; STT stays `language_code=auto` on every call. Reply-language
   override is passed explicitly to the LLM (`reply_language=`) with an
   exact per-call instruction, including code-mixed Hinglish/Tanglish.
   Knowledge-limitation phrasing updated to: "I don't have the current
   plan details in this prototype yet. I can still help with general
   support questions."
3. **Deterministic end-call intent (fixes issue C).** Extended
   `END_PHRASES` (English + Tanglish/Tamil: "cut the call", "cut this
   call", "end the call", "disconnect the call", "hang up",
   "call cut pannunga", "call-a cut pannunga", "phone-a cut pannunga",
   "call cut pannu", …). Closing message is spoken first ("Thank you for
   contacting Zhatura. Have a great day."), then `transport.close()` —
   closing the WSS advances the Exotel flow to the **Hangup applet**.
   `receive()` now raises `TransportClosed` when the socket ends, so
   every end path (voice end-call, Exotel stop, silence timeout,
   duplicate defense) converges on the same cleanup. Non-end negatives
   ("My call got disconnected yesterday") do not close the call.
4. **Idempotent cleanup + duplicate defense (fixes issue D).** A
   `_finalized` flag makes `shutdown()` provably single-shot; an
   externally-triggered shutdown cancels the parked `_run_task` so the
   handler always returns and `active_calls` always drains; a
   `stream_sid → CallSession` registry shuts down a stale session when
   the same `stream_sid` reconnects (`duplicate_stream_replaced`
   reason); every path logs `SESSION CLEANUP START/COMPLETE` and
   `ACTIVE CALLS: n`.

## 5. Audio Configuration (current)

| Setting | Value |
|---|---|
| Exotel media rate (`?sample-rate=`) | 16000 Hz (Voicebot URL parameter; 8000 supported for fallback A/B) |
| Exotel frame | 100 ms = 3200 B (16 kHz mono linear16) |
| Sarvam TTS decode rate | 22050 Hz (sink input), resampled linearly to the Exotel rate on send |
| Pacing | one media frame per 100 ms, real-time cadence (pacer loop task) |
| Buffer bound | 15 s of unsent audio (dropped with a warning beyond that; barge-in clears) |
| Playback completion | Exotel `mark` echo (bounded 45 s wait if no echo arrives) |

Per-utterance evidence line (server log):

```text
TTS OUT: rate=22050 frame=4410B/100ms chunks=35 bytes=154350 max_buffer=153648B
```

The PCM self-test (automated) proves byte-exact reconstruction: fixed
PCM → Exotel media frames → reconstructed PCM is identical to the source
(no loss, no duplication, no gaps), at both pacing widths.

## 6. Language Switching (live verification, real Sarvam)

| Caller said | Detected | Result |
|---|---|---|
| "Can you speak in Tamil?" | switch → `ta-IN` | AI: "நிச்சயமாக, நான் தமிழில் பேசுகிறேன். உங்களுக்கு என்ன உதவி வேண்டும்?" (Tamil script, `ta-IN` TTS) |
| then spoke Tamil | STT auto → `ta-IN` | AI: "நான் உங்களுக்கு உதவ இங்கே இருக்கிறேன்…" |
| (call log) | — | `language: "ta-IN"` recorded |

Automated matrix also covers: "Speak Tamil.", "Tamil please, can we
switch?", "Can we continue in Hindi?", "Hindi mein baat karo.", "Please
switch to Hindi", "Can you switch back to English?", "தமிழில் பேச
முடியுமா?" — and the false-positive guard set ("I am learning Tamil on
Zhatura.", "Do you have Tamil chess lessons?", "My son studies in a
Hindi medium school.", "The English course is good.").

## 7. End Call Flow (live verification)

Caller says "Can you cut the call?" — server log, ~4 s from detection to
full cleanup:

```text
END_CALL DETECTED.
CLOSING MESSAGE SENT.          → "Thank you for contacting Zhatura. Have a great day."
WSS CLOSING (bot end-call).    → Exotel advances to the Hangup applet
Call disconnected (TransportClosed).
SESSION CLEANUP COMPLETE. reason=user_end_phrase turns=2
```

Simulated client confirmed: **server closed the WSS**; call log records
`disconnect_reason: user_end_phrase`. Voice end-call, Exotel stop,
silence timeout, caller disconnect and duplicate-session shutdown all
converge on this same cleanup path.

## 8. Cleanup (live verification)

- `active_calls` polled to **0** after each of the 3 sequential calls
  (and asserted 0 before the first).
- Registry is empty after every call; call log written exactly once per
  call (`_finalized` guard is idempotent under repeated `shutdown()`).
- Duplicate `stream_sid` reconnect: stale session finalized
  (`duplicate_stream_replaced`), new session owns the registry entry,
  `active_calls` returns to 0.

## 9. Sequential Call Tests (§14 — not PASS after one call)

`prototype/phase4_stabilization_live_check.py` (real Sarvam, real server,
Exotel-faithful simulated telephony, 5 s gaps between calls):

```text
CALL 1: English turns + voice end-call   — 6/6 PASS
CALL 2: English → explicit Tamil switch  — 4/4 PASS
CALL 3: barge-in + stop                  — 3/3 PASS
STABILIZATION LIVE CHECK: PASS
```

Measured per-turn latencies on these calls (speech end → first Exotel
media): greeting ~1.3 s; turns **1249–1568 ms** (LLM 663–939 ms,
TTS first audio 324–374 ms). Same order as pre-stabilization — pacing
adds no perceptible start latency (~40 ms), it only evens out delivery.

## 10. Real Call Audio Quality

Pending your PSTN re-test — this is strictly your part (I cannot place
phone calls). Re-run the §21/§23 matrix: Call 1 (English, ≥3 turns, end
by voice "cut the call"), Call 2 (explicit Tamil switch), Call 3
(barge-in), then repeat all three. Per §25, if voice still sounds
degraded at 16 kHz, change the Voicebot applet WSS URL to
`?sample-rate=8000` (see docs/EXOTEL_PHASE4_SETUP.md §7) and compare;
report which rate sounds smoother.

## 11. Barge-In Regression

Still works after buffering: caller audio mid-playback cancels the sink
(clears the buffer, Exotel `clear` sent), and the live Call 3 observed
`clear` + an immediate new reply. Automated pacing test asserts ≤ 2
in-flight frames after cancel (≈ 3.5 s of buffered audio does NOT drain
out after barge-in). Base `phase4_live_call_check.py` re-ran green with
`[clear]` events on the interrupted turn.

## 12. Automated Tests

**182 passed, 0 failed** (~10 s), all mock-only — no Exotel, no ngrok,
no Sarvam credits. New stabilization tests (42) cover: end-call phrases
and negatives, language-switch detection and false positives, session
language state, TTS language follows reply language, fixed-frame PCM
integrity + real-time pacing + partial-tail flush, PCM→media→PCM
reconstruction, 16k→8k resampling, barge-in buffer flush, end-call
closes the socket at both `_respond` and full `run()` level, shutdown
idempotency, 3 sequential TestClient calls with `active_calls` 0→1→0 and
registry drain, duplicate `stream_sid` defense.

## 13. Security

- Sarvam key untouched: only in local `.env` (git-ignored); never
  printed, logged, or committed; no keys in chat or this report.
- No Exotel API secrets configured or needed for this inbound flow.
- No ngrok token in repo, chat, `.env`, or any report (token lives only
  in ngrok's own config).
- Logs: no base64 dumps, no raw audio, no caller numbers — event counts
  and byte sizes only (`TTS OUT` metrics are counters).
- Call logs contain transcripts and timing only.

## 14. Remaining Issues

- **User-side re-verification on a real PSTN call** (audio quality at
  16 kHz vs 8 kHz, Tamil switch, voice hangup, repeated calls) — the
  only gate left for full PASS.
- ngrok free-URL changes on restart (documented; update the Voicebot
  applet URL whenever the tunnel restarts).
- Exotel trial limits (verified callee numbers, trial-call behavior)
  unchanged and documented in EXOTEL_PHASE4_SETUP.md §8.
- Knowledge-limitation replies are intentionally shallow ("I don't have
  the current plan details in this prototype yet…") until a later phase
  adds the Zhatura knowledge base (RAG) — out of scope here.

## 15. Phase 4 Ready for PASS?

**Pending your real-call confirmation.** Code-side, everything the real
calls exposed is fixed and re-verified at the protocol level with real
Sarvam; the only unverifiable-by-me item is how it actually sounds and
behaves on the phone. Per the standing rule the status stays PARTIAL
until you place (or repeat) the Call 1/2/3 matrix and it passes for you.

## 16. Ready for Phase 5?

**NO** — Phase 5 is explicitly out of scope until Phase 4 is PASS on a
real call.
