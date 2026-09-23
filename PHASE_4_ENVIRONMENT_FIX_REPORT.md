# Phase 4 Environment Fix Report

Date: 2026-09-22

## Status

**PARTIAL** — ngrok authentication is the only blocker. This is a
user-side manual step, **not a code failure**. Everything else is in
the fully-ready state (STATE B per the task definition).

## Port 8000

```text
Process Found:   YES
PID:             46180
Process:         Python -u prototype/phase4_exotel_server.py
                 (the existing Phase 4 server started earlier)
Phase 4 Server:  YES — identified before any action; nothing killed
Health:          HEALTHY
```

The `[Errno 48] address already in use` conflict is expected behavior:
the Phase 4 server was already running in the background. Per the task
rule, the already-running healthy server is reused; no second server
was started and the port was not changed.

## Action Taken

- Verified project directory and Python 3.14.6.
- Identified port 8000 owner with `lsof` — confirmed it is the Phase 4
  server (`prototype/phase4_exotel_server.py`).
- Verified its `/health` — healthy; kept it running.
- Checked ngrok: installed, but no config/authtoken present.
- Added a safe read-only helper: `scripts/check_phase4_environment.sh`
  (checks port 8000, `/health`, ngrok install/auth/tunnel, prints the
  WSS URL when a tunnel exists; contains no secrets, kills no
  processes).
- Re-ran the full test suite — no regressions.
- No Phase 4 code was modified (`agent/`, `speech/`, `transports/`,
  `telephony/` untouched).

## Local Health Check

```bash
curl -s http://localhost:8000/health
```

```json
{"status":"healthy","sarvam":"configured","phase":4,"active_calls":0}
```

The `/ws` WebSocket route also accepts connections (direct handshake
probe: OK).

## ngrok

```text
Installed:      YES
Version:        3.39.11 (/opt/homebrew/bin/ngrok)
Authentication: NO — ngrok config file does not exist;
                "ngrok config check" → stat .../ngrok/ngrok.yml: no such file or directory
Tunnel:         NOT RUNNING (cannot start without an authtoken)
Public URL:     NOT AVAILABLE until authentication
```

Authtoken is not recorded here or anywhere in the repository.

## Public Health Check

NOT TESTED — no tunnel exists yet (blocked by ngrok authentication).

## WSS URL

NOT AVAILABLE UNTIL NGROK AUTHENTICATION. Once the tunnel runs, the
URL will be:

```text
wss://<actual-ngrok-domain>/ws?sample-rate=16000
```

No API keys, tokens or secrets will ever appear in this URL (the
helper script derives and prints it automatically).

## Tests

`pytest prototype/tests` → **140 passed / 0 failed**. Coverage
unchanged; no tests removed or weakened.

## Security

```text
.env ignored:                  YES (git check-ignore confirmed)
ngrok token found in repository: NO (repo-wide scan for authtoken
                               storage patterns: clean)
Secrets exposed:               NO
```

## Remaining Manual Step

One step, yours only — never share the token in chat; I must not and
will not ask for or store it:

1. Get your authtoken from the ngrok dashboard
   (dashboard.ngrok.com → Your Authtoken).
2. Run once:

   ```bash
   ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
   ```

3. Start the tunnel:

   ```bash
   ngrok http 8000
   ```

4. Verify in one check:

   ```bash
   bash scripts/check_phase4_environment.sh
   ```

   It prints the public URL and the exact WSS URL to paste into the
   Exotel Voicebot applet, then follows with
   `docs/EXOTEL_PHASE4_SETUP.md` §4–6 for the real phone call.

## Ready for Exotel Dashboard Configuration?

**NO** — pending the single ngrok authtoken step above. After it:
YES, the server is already running and healthy.
