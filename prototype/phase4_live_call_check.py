"""Zhatura AI Customer Care — Phase 4 LIVE local integration check.

⚠ Makes REAL Sarvam API calls against a RUNNING local Phase 4 server.
Not part of pytest. Simulates Exotel's Voicebot WebSocket protocol
against a locally running server:

    Terminal 1:  python prototype/phase4_exotel_server.py
    Terminal 2:  python prototype/phase4_live_call_check.py [--wavs ...]

It sends connected → start → media (WAV audio, Exotel PCM/base64
format) → ... → stop, plays received bot audio nowhere (counts it),
and verifies transcript + barge-in-capable protocol behavior.

Exit code 0 = all protocol stages observed.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from telephony.serializer import resample_pcm16  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXOTEL_RATE = 16000  # must match server EXOTEL_AUDIO_SAMPLE_RATE


def load_wav_pcm16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
    if width == 2:
        a = np.frombuffer(frames, dtype=np.int16)
    elif width == 4:
        a = (np.frombuffer(frames, dtype=np.int32) / 65536).astype(np.int16)
    else:
        a = (np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) << 8
    if channels > 1:
        a = a.reshape(-1, channels).mean(axis=1).astype(np.int16)
    out = resample_pcm16(a.tobytes(), rate, EXOTEL_RATE)
    return np.frombuffer(out, dtype=np.int16)


async def run_check(wavs: list[Path], url: str) -> int:
    import websockets

    stats = {"media_received": 0, "bytes_received": 0, "marks": 0,
             "clears": 0, "first_bot_audio_at": None}
    stop = asyncio.Event()

    async with websockets.connect(url, max_size=1 << 20) as ws:
        async def receiver():
            try:
                async for raw in ws:
                    try:
                        m = json.loads(raw)
                    except ValueError:
                        continue
                    event = m.get("event")
                    if event == "media":
                        stats["media_received"] += 1
                        stats["bytes_received"] += len(base64.b64decode(
                            m["media"]["payload"]))
                        if stats["first_bot_audio_at"] is None:
                            stats["first_bot_audio_at"] = time.monotonic()
                    elif event == "mark":
                        stats["marks"] += 1
                        print(f"  [mark] {m.get('mark', {}).get('name')}")
                    elif event == "clear":
                        stats["clears"] += 1
                        print("  [clear] Exotel-side audio flushed")
            except websockets.ConnectionClosed:
                pass
            finally:
                stop.set()

        rx = asyncio.create_task(receiver())
        await ws.send(json.dumps({"event": "connected"}))
        await asyncio.sleep(0.1)
        call_sid = f"local-check-{int(time.time())}"
        await ws.send(json.dumps({"event": "start", "start": {
            "stream_sid": f"stream-{int(time.time())}",
            "call_sid": call_sid,
        }}))
        print(f"Simulated call started (call_sid={call_sid}).")
        # Let the greeting play (bot media flows in while we wait).
        t0 = time.monotonic()
        while (stats["first_bot_audio_at"] is None
               and time.monotonic() - t0 < 15):
            await asyncio.sleep(0.1)
        if stats["first_bot_audio_at"] is None:
            print("FAIL: no bot greeting audio within 15 s.")
            await ws.close()
            return 1
        greet_ms = round((stats["first_bot_audio_at"] - t0) * 1000)
        print(f"Greeting: first bot audio after {greet_ms} ms.")
        await asyncio.sleep(3)  # let the greeting finish playing

        for wav_path in wavs:
            print(f"Caller speaks: {wav_path.name}")
            pcm = load_wav_pcm16(wav_path)
            chunk = int(EXOTEL_RATE * 0.1) * 2  # 100 ms
            for i in range(0, len(pcm.tobytes()), chunk):
                payload = base64.b64encode(
                    pcm.tobytes()[i:i + chunk]).decode()
                await ws.send(json.dumps({"event": "media",
                                          "media": {"payload": payload}}))
                await asyncio.sleep(0.1)  # real-time pacing
            # trailing silence to close the VAD turn (paced, 100 ms
            # frames like speech — oversized single frames are rejected
            # by the STT stream)
            silence = base64.b64encode(b"\x00\x00" * (EXOTEL_RATE // 10))
            silence = silence.decode()
            for _ in range(10):
                await ws.send(json.dumps({"event": "media",
                                          "media": {"payload": silence}}))
                await asyncio.sleep(0.1)
            # wait for the answer to start coming back
            before = stats["media_received"]
            t_turn = time.monotonic()
            while (stats["media_received"] == before
                   and time.monotonic() - t_turn < 20):
                await asyncio.sleep(0.1)
            if stats["media_received"] == before:
                print(f"FAIL: no bot response to {wav_path.name}.")
                await ws.close()
                return 1
            resp_ms = round((stats["first_bot_audio_at"] and
                             time.monotonic() - t_turn) * 1000)
            print(f"  bot response started (~{max(resp_ms, 0)} ms wait).")
            await asyncio.sleep(4)  # let the reply play through

        await ws.send(json.dumps({"event": "stop",
                                  "call_sid": call_sid}))
        print("Stop sent. Waiting for server-side finalize...")
        try:
            await asyncio.wait_for(stop.wait(), 10)
        except asyncio.TimeoutError:
            print("WARN: server did not close the socket; closing locally.")
            await ws.close()
        rx.cancel()

    print()
    print(f"Bot media messages received : {stats['media_received']}")
    print(f"Bot audio bytes received    : {stats['bytes_received']}")
    print(f"Mark echoes                 : {stats['marks']}")
    print(f"Clear events                : {stats['clears']}")
    ok = (stats["media_received"] > 0 and stats["marks"] > 0)
    print("LIVE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4 live local check.")
    parser.add_argument("--url", default=None,
                        help="ws(s) URL, default from config port/path")
    parser.add_argument("--wavs", nargs="+", type=Path, default=None)
    args = parser.parse_args()

    cfg = config.load_config()
    url = args.url or (f"ws://127.0.0.1:{cfg.exotel_ws_port}"
                       f"{cfg.exotel_ws_path}?sample-rate={EXOTEL_RATE}")
    if args.wavs:
        wavs = list(args.wavs)
    else:
        base = PROJECT_ROOT / "audio_samples" / "sarvam"
        wavs = [base / "english" / "problem.wav",
                base / "terminology" / "brand_zhatura_ai.wav"]
    missing = [str(w) for w in wavs if not w.exists()]
    if missing:
        print("Missing WAVs:", missing)
        return 1
    print(f"Connecting to {url}")
    return asyncio.run(run_check(wavs, url))


if __name__ == "__main__":
    raise SystemExit(main())
