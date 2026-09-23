# Phase 4 — Exotel Telephony Setup Guide

This guide connects the Zhatura AI voice agent to a real telephone call
using **Exotel's Voicebot Applet**.

```text
Caller ──PSTN──► Exotel trial number ──App Bazaar flow──► Voicebot applet
                                                              │  WSS
                                    ┌─────────────────────────┘
                                    ▼
                    ngrok (dev tunnel) ──► our server :8000 /ws
                                              │
                    Phase 3 agent: Realtime STT → sarvam-105b-conversations → TTS
```

## 1. Prerequisites

| Item | Where |
|---|---|
| Running Phase 4 server | `python prototype/phase4_exotel_server.py` |
| Public WSS URL (dev) | `ngrok http 8000` (free account is fine) |
| Exotel account with **Voicebot Applet** | Exotel dashboard → App Bazaar |

**No Exotel API credentials are needed inside the bot.** All call
identifiers (`call_sid`, `stream_sid`, custom parameters) arrive inside
the WebSocket `start` message. Do *not* add `EXOTEL_API_KEY` /
`EXOTEL_API_TOKEN` / `EXOTEL_ACCOUNT_SID` to `.env`.

The only Sarvam key stays server-side (existing `SARVAM_API_KEY` in
`.env`); it never appears in the Exotel URL, dashboard, or any log.

## 2. Start the server

```bash
source .venv/bin/activate
python prototype/phase4_exotel_server.py
```

Check it is up:

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","sarvam":"configured","phase":4,"active_calls":0}
```

## 3. Expose it with ngrok (development)

```bash
ngrok http 8000
```

ngrok prints a forwarding URL such as:

```text
https://abc123xyz.ngrok-free.app  →  http://localhost:8000
```

Your Voicebot WebSocket URL is therefore:

```text
wss://abc123xyz.ngrok-free.app/ws?sample-rate=16000
```

Notes:

- Use `wss://` (TLS). ngrok terminates TLS, so no certificates are
  needed on our side.
- **Free ngrok URLs change on every restart.** Whenever ngrok restarts
  you must update the URL in the Exotel App Bazaar flow (step 4). This
  is acceptable for a trial; production should use a fixed domain.
- The URL contains **no secrets** — only the public tunnel host and the
  WebSocket path.
- `?sample-rate=16000` selects 16 kHz linear16 PCM, matching the
  Phase 3 STT format exactly (no input resampling loss). Valid values:
  `8000`, `16000`, `24000`. If your Exotel account ignores the
  parameter, the server still handles 8 kHz input — set
  `EXOTEL_AUDIO_SAMPLE_RATE=8000` in `.env` so the server expects the
  right format, and leave the query parameter off the URL. The server
  resamples internally either way.

## 4. Exotel App Bazaar flow

In the Exotel dashboard, create an **App Bazaar** app (not a plain
"Connect an app" passthrough):

1. **Call Start** → **Voicebot Applet** → **Hangup**.
2. In the Voicebot applet's *WebSocket URL* field, paste:

   ```text
   wss://<your-ngrok-subdomain>.ngrok-free.app/ws?sample-rate=16000
   ```

   Important: use the **Voicebot** applet, **not** the **Stream**
   applet. The Stream applet is unidirectional and cannot receive bot
   audio back.
3. Leave custom parameters empty for the prototype (any key/value pairs
   you add are safely logged — keys are truncated, caller numbers are
   never stored).
4. Save the app.

If the **Voicebot applet is not available** in your trial account,
Phase 4 cannot be completed with a real call — see
*Trial limitations* below and `PHASE_4_REPORT.md`
("Blocked by Exotel account provisioning").

## 5. Assign a phone number (ExoPhones)

1. Dashboard → **ExoPhones** → pick your trial number.
2. Edit the number → set the *App Bazaar* app from step 4 as the
   number's call flow.
3. Save.

Do **not** hard-code this number into any code or config. If you want it
recorded for your own convenience, `EXOTEL_PHONE_NUMBER=` in `.env` is
an optional free-text field only; the server does not read it.

## 6. Place the real call

1. Keep the server and ngrok running.
2. Call the ExoPhone number from a phone.
3. Expected conversation:
   - Bot greets: "Hello, welcome to Zhatura customer support…".
   - Speak in English first (e.g. "I have a problem with my account").
   - Bot replies within roughly 1–2 s of you stopping.
   - **Barge-in:** start talking while the bot is speaking — the bot
     should stop immediately (server sends Exotel `clear`) and listen.
   - Say "bye" to end, or simply hang up — either way the server
     finalizes the call log.
4. After the call, inspect the log:

   ```bash
   ls prototype/logs/calls/
   ```

## 7. Local end-to-end check (no phone, real Sarvam)

Before burning a real call, verify the full protocol locally:

```bash
python prototype/phase4_exotel_server.py        # terminal 1
python prototype/phase4_live_call_check.py      # terminal 2
```

The checker simulates Exotel: it streams WAV files as 100 ms
`media` events, verifies greeting audio, per-turn bot replies, mark
echoes, and clean finalization. Exit code 0 = PASS.

## 8. Language testing on the phone

- **English first.** Only after an English call works end to end,
  retry with **Tamil**, **Hindi**, **Hinglish**, or **Tanglish**
  phrases — the STT runs in `auto` mode and the prompt explicitly
  covers these registers.
- The deterministic brand correction already handles Exotel-side
  mishearings of "Zhatura" in Latin, Devanagari and Tamil scripts.

## 9. Human transfer (prototype scope)

A caller saying "human" / "representative" is acknowledged politely and
the call is flagged `human_requested=true` in the call log. No actual
transfer is performed in the prototype — a production deployment would
chain a **Connect** applet after the Voicebot applet and signal
escalation via a custom parameter.

## 10. Passthru applet (documentation only)

For production, the Exotel **Passthru** applet can post call metadata
(caller number masked, call status) to our service before the Voicebot
applet runs. It is intentionally **not** part of this prototype: the
Voicebot `start` message already carries everything the agent needs.

## 11. Trial limitations checklist

Confirm these on your Exotel trial before testing:

- [ ] Voicebot Applet visible in App Bazaar
- [ ] Trial ExoPhone number assignable to an App Bazaar app
- [ ] Outbound PSTN calls allowed to your personal number
- [ ] Call duration limits (trials often cap at a few minutes)

## 12. Shutdown

Ctrl+C the server and ngrok. In-flight calls are finalized with
`disconnect_reason` set and their logs written to
`prototype/logs/calls/`.
