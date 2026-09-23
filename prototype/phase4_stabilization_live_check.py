"""Zhatura Phase 4 stabilization LIVE check (uses real Sarvam API).

Sequential simulated-Exotel calls against a RUNNING local server to
verify the real-call fixes:

    Call 1: 2 English turns + end call BY VOICE ("cut the call")
            → expect bot closing audio, then server closes the WSS.
    Call 2: English turn → explicit Tamil switch → Tamil reply
            (verified via the assistant text in the server-side call
            log, which must contain Tamil script).
    Call 3: barge-in during bot reply (caller audio while bot speaks)
            → expect a `clear` event; then stop.

Between calls, /health active_calls must return to 0 (spec §13/§14).

Exotel fidelity: real Exotel echoes every `mark` request once it has
played the buffered audio. This client echoes marks immediately after
receiving them, so the server's playback-completion wait (bounded at
45 s without an echo) resolves at real-time cadence — the same shape
a real call has. It also waits for bot audio to go idle before
speaking, exactly like a polite caller.

    Terminal 1:  python prototype/phase4_exotel_server.py
    Terminal 2:  python prototype/phase4_stabilization_live_check.py

Exit code 0 = all scenarios behaved as expected.
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from phase4_live_call_check import load_wav_pcm16  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
SAMPLES = ROOT / "audio_samples" / "sarvam"


def active_calls(port: int) -> "int | None":
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            return json.loads(resp.read())["active_calls"]
    except Exception:
        return None


class CallResult:
    def __init__(self):
        self.media = 0
        self.marks = 0
        self.clears = 0
        self.server_closed = False


async def _echo_marks_and_count(ws, result: CallResult, stopped,
                                _exc):
    """Inbound loop: count bot events; echo marks like real Exotel."""
    try:
        async for raw in ws:
            m = json.loads(raw)
            ev = m.get("event")
            if ev == "media":
                result.media += 1
            elif ev == "mark":
                result.marks += 1
                # Real Exotel echoes a mark after playout; echo now.
                name = (m.get("mark") or {}).get("name")
                if name:
                    try:
                        await ws.send(json.dumps(
                            {"event": "mark", "mark": {"name": name}}))
                    except Exception:
                        return
            elif ev == "clear":
                result.clears += 1
    except _exc:
        pass
    finally:
        # The inbound loop only ends when the connection closes. This
        # client never initiates close before `stopped` is set except on
        # explicit timeout aborts, so reaching here = the server closed
        # (bot end-call / stop-event cleanup). Clean closes end the
        # async-for without raising, so detect in finally, not except.
        result.server_closed = True
        stopped.set()


async def _send_wav(ws, result: CallResult, stopped,
                    wav: Path,
                    wait_audio: bool = True) -> int:
    """Speak a WAV like a caller; wait for the bot to start replying."""
    before = result.media
    pcm = load_wav_pcm16(wav)
    chunk = int(RATE * 0.1) * 2
    data = pcm.tobytes()
    for i in range(0, len(data), chunk):
        await ws.send(json.dumps({"event": "media", "media": {
            "payload": base64.b64encode(data[i:i + chunk]).decode()}}))
        await asyncio.sleep(0.1)
    # trailing silence so VAD closes the turn
    silence = base64.b64encode(b"\x00\x00" * (RATE // 10)).decode()
    for _ in range(10):
        await ws.send(json.dumps({"event": "media",
                                  "media": {"payload": silence}}))
        await asyncio.sleep(0.1)
    if not wait_audio:
        return 0
    t_turn = time.monotonic()
    while (result.media == before
           and time.monotonic() - t_turn < 25
           and not stopped.is_set()):
        await asyncio.sleep(0.1)
    return result.media - before


async def _wait_audio_idle(result: CallResult, idle_s: float = 1.2,
                           timeout_s: float = 20) -> None:
    """A polite caller waits until the bot stops talking before
    speaking again (bot frames arrive at real-time cadence)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        last = result.media
        await asyncio.sleep(idle_s)
        if result.media == last:
            return
    return


async def run_call(rng_label: str, url: str,
                   wavs: "list[Path]",
                   end_voice_wav: "Path | None" = None,
                   barge_in_at_reply: bool = False) -> CallResult:
    import websockets

    result = CallResult()
    stopped = asyncio.Event()

    async with websockets.connect(url, max_size=1 << 20) as ws:
        rx = asyncio.create_task(
            _echo_marks_and_count(ws, result, stopped,
                                  websockets.ConnectionClosed))
        await ws.send('{"event":"connected"}')
        await asyncio.sleep(0.1)
        ts = int(time.time())
        await ws.send(json.dumps({"event": "start", "start": {
            "stream_sid": f"stab-{ts}", "call_sid": f"stab-call-{ts}"}}))

        # greeting: wait for it to start, then for it to FINISH playing
        t0 = time.monotonic()
        while result.media == 0 and time.monotonic() - t0 < 15:
            await asyncio.sleep(0.1)
        if result.media == 0:
            await ws.close()
            raise RuntimeError(f"{rng_label}: no greeting audio in 15 s")
        await _wait_audio_idle(result)

        for i, wav in enumerate(wavs):
            is_barge = barge_in_at_reply and i == len(wavs) - 1
            # barge-in: speak at once (bot reply to the previous turn is
            # mid-playout); normal turns: speak after audio went idle.
            if not is_barge:
                await _wait_audio_idle(result, idle_s=0.6, timeout_s=15)
            await _send_wav(ws, result, stopped, wav)
            await asyncio.sleep(1)

        if end_voice_wav is not None:
            await _wait_audio_idle(result, idle_s=0.6, timeout_s=15)
            await _send_wav(ws, result, stopped, end_voice_wav)
            # end-call: server plays the closing message, then closes.
            try:
                await asyncio.wait_for(stopped.wait(), 30)
            except asyncio.TimeoutError:
                result.server_closed = False
        else:
            await ws.send(json.dumps({"event": "stop",
                                      "call_sid": f"stab-call-{ts}"}))
            try:
                await asyncio.wait_for(stopped.wait(), 10)
            except asyncio.TimeoutError:
                await ws.close()
        rx.cancel()
    return result


def latest_call_log(before: "set[str]", timeout: float = 10) -> "Path | None":
    """Poll until a NEW call log appears (cleanup writes it at the end
    of the handler; active_calls==0 is the ordering gate first)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = set(glob.glob(str(ROOT / "prototype/logs/calls/call-*.json")))
        new = [p for p in logs - before]
        if new:
            return Path(max(new, key=os.path.getmtime))
        time.sleep(0.2)
    return None


async def main() -> int:
    cfg = config.load_config()
    url = (f"ws://127.0.0.1:{cfg.exotel_ws_port}{cfg.exotel_ws_path}"
           f"?sample-rate={RATE}")
    ok = True

    def check(label, cond):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'} — {label}")
        if not cond:
            ok = False

    def wait_idle_calls(label: str) -> bool:
        """Poll active_calls to 0 for up to 10 s (cleanup gate)."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            n = active_calls(cfg.exotel_ws_port)
            if n == 0:
                return True
            time.sleep(0.3)
        return False

    if active_calls(cfg.exotel_ws_port) != 0:
        print("ERROR: active_calls != 0 before testing — "
              "a previous session leaked.")
        return 1

    # ---- Call 1: English, end by voice --------------------------------
    before = set(glob.glob(str(ROOT / "prototype/logs/calls/call-*.json")))
    print("CALL 1: English turns + voice end-call")
    r1 = await run_call(
        "call-1", url,
        [SAMPLES / "english/problem.wav", SAMPLES / "english/account_help.wav"],
        end_voice_wav=SAMPLES / "english/cut_the_call.wav")
    check("greeting + turns produced audio", r1.media > 20)
    check("mark events exchanged (mark + echo)", r1.marks >= 2)
    check("server closed WSS after voice end-call", r1.server_closed)
    check("active_calls == 0 after call 1", wait_idle_calls("call 1"))
    log1 = latest_call_log(before)
    if log1:
        data = json.loads(log1.read_text())
        check("call log end reason = user_end_phrase",
              data.get("disconnect_reason") == "user_end_phrase")
        check("closing message spoken",
              any("Thank you for contacting" in (t.get("text") or "")
                  for t in data.get("turns", [])))
    else:
        check("call 1 log written", False)
    await asyncio.sleep(5)

    # ---- Call 2: English → Tamil switch --------------------------------
    before = set(glob.glob(str(ROOT / "prototype/logs/calls/call-*.json")))
    print("CALL 2: English → explicit Tamil switch")
    r2 = await run_call(
        "call-2", url,
        [SAMPLES / "english/problem.wav",
         SAMPLES / "english/language_switch_tamil.wav",
         SAMPLES / "tamil/problem.wav"])
    check("call 2 produced audio", r2.media > 20)
    check("active_calls == 0 after call 2", wait_idle_calls("call 2"))
    log2 = latest_call_log(before)
    if log2:
        data = json.loads(log2.read_text())
        tamil_reply = any(
            any("஀" <= ch <= "௿" for ch in (t.get("text") or ""))
            for t in data.get("turns", []) if t.get("speaker") == "assistant")
        check("assistant replied in Tamil script after switch request",
              tamil_reply)
        check("session language recorded", data.get("language") == "ta-IN")
    else:
        check("call 2 log written", False)
    await asyncio.sleep(5)

    # ---- Call 3: barge-in + clean stop ---------------------------------
    print("CALL 3: barge-in + stop")
    r3 = await run_call(
        "call-3", url,
        [SAMPLES / "english/problem.wav",
         SAMPLES / "english/subscription.wav"],
        barge_in_at_reply=True)
    check("call 3 produced audio", r3.media > 10)
    check("clear event sent on barge-in/cancel", r3.clears >= 1)
    check("active_calls == 0 after call 3", wait_idle_calls("call 3"))

    print()
    print("STABILIZATION LIVE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
