#!/usr/bin/env bash
# Phase 4 environment check — read-only.
# Checks: Phase 4 server on :8000, /health, ngrok install + auth.
# Contains no secrets. Kills nothing. Modifies nothing.
set -u

fail=0

echo "== Phase 4 server (port 8000) =="
if PID=$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null | head -1); then
    PROC=$(ps -p "$PID" -o command= 2>/dev/null | cut -c1-120)
    echo "listening PID: $PID"
    echo "process:       $PROC"
else
    echo "NOT LISTENING — start with: python prototype/phase4_exotel_server.py"
    fail=1
fi

echo
echo "== Local /health =="
if HEALTH=$(curl -sf --max-time 5 http://localhost:8000/health 2>/dev/null); then
    echo "$HEALTH"
else
    echo "FAIL — /health not reachable"
    fail=1
fi

echo
echo "== ngrok =="
if command -v ngrok >/dev/null 2>&1; then
    echo "installed: $(ngrok version 2>/dev/null)"
    if ngrok config check >/dev/null 2>&1; then
        echo "auth:      OK (config valid)"
    else
        echo "auth:      MISSING — run: ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>"
        fail=1
    fi
    if curl -sf --max-time 3 http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
        PUB=$(curl -s http://127.0.0.1:4040/api/tunnels \
            | grep -o '"public_url":"https://[^"]*"' | head -1 \
            | cut -d'"' -f4)
        echo "tunnel:    RUNNING ($PUB)"
        if [ -n "${PUB:-}" ]; then
            HOST=${PUB#https://}
            echo "WSS URL:   wss://${HOST}/ws?sample-rate=16000"
            if PUBHEALTH=$(curl -sf --max-time 8 "${PUB}/health" 2>/dev/null); then
                echo "public /health: $PUBHEALTH"
            else
                echo "public /health: FAIL"
                fail=1
            fi
        fi
    else
        echo "tunnel:    NOT RUNNING — after auth: ngrok http 8000"
    fi
else
    echo "installed: NO — brew install ngrok"
    fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "ENVIRONMENT: READY"
else
    echo "ENVIRONMENT: NOT READY (see items above)"
fi
exit "$fail"
