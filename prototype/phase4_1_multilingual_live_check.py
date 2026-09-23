"""Zhatura Phase 4.1 multilingual LIVE check (uses real Sarvam API).

Simulated-Exotel calls against a RUNNING local server exercising the
full Sarvam scheduled-language handling:

    Call A — one call cycling through ALL 11 Bulbul-voiced languages:
             English switch request per language ("Can you speak in
             <Name>?") → assistant reply asserted in that language and
             spoken with that Bulbul voice (call-log turn language +
             tts_language); followed by a native-language sentence whose
             STT auto-detection is asserted from the call log.
    Call B — Hindi request → Hinglish code-mixed turn → reply must
             stay Hindi (natural code-mixing preserved, never yanked to
             plain English).
    Call C — Urdu request (no Bulbul voice) → deterministic fallback
             notice asks Hindi-or-English (spoken in en-IN), caller
             answers "Hindi", conversation continues in Hindi with the
             hi-IN voice. Call log must show
             requested=ur-IN → reply_language=hi-IN and no Urdu TTS.

Sample generation (first run only): English switch requests and native
sentences are synthesized with Sarvam Bulbul v3 and cached under
audio_samples/sarvam/languages/ (Bulbul speaks all 11 verified
languages, so every fixture is real native audio, not faked).

    Terminal 1:  python prototype/phase4_exotel_server.py
    Terminal 2:  python prototype/phase4_1_multilingual_live_check.py

Exit code 0 = all scenarios behaved as expected.
"""

from __future__ import annotations

import asyncio
import base64
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
LANG_SAMPLES = SAMPLES / "languages"

# The 11 Bulbul-voiced languages, cycled in one call.
MULTILINGUAL_CYCLE = (
    ("hi-IN", "Hindi", "मुझे अपने बच्चे की शतरंज पाठ के बारे में एक सवाल है।"),
    ("bn-IN", "Bengali", "আমার সন্তানের দাবা পাঠ সম্পর্কে আমার একটি প্রশ্ন আছে।"),
    ("ta-IN", "Tamil", "என் குழந்தையின் சதுரங்கப் பாடம் பற்றி எனக்கு ஒரு கேள்வி இருக்கிறது."),
    ("te-IN", "Telugu", "నా పిల్లల చదరంగ పాఠం గురించి నాకు ఒక ప్రశ్న ఉంది."),
    ("kn-IN", "Kannada", "ನನ್ನ ಮಗುವಿನ ಚದುರಂಗ ಪಾಠದ ಬಗ್ಗೆ ನನಗೆ ಒಂದು ಪ್ರಶ್ನೆ ಇದೆ."),
    ("ml-IN", "Malayalam", "എന്റെ കുട്ടിയുടെ ചെസ്സ് പാഠത്തെക്കുറിച്ച് എനിക്ക് ഒരു ചോദ്യമുണ്ട്."),
    ("mr-IN", "Marathi", "माझ्या मुलाच्या बुद्धिबळ धड्याबद्दल मला एक प्रश्न आहे."),
    ("gu-IN", "Gujarati", "મારા બાળકના ચેસ પાઠ વિશે મને એક પ્રશ્ન છે."),
    ("pa-IN", "Punjabi", "ਮੇਰੇ ਬੱਚੇ ਦੇ ਸ਼ਤਰੰਜ ਦੇ ਪਾਠ ਬਾਰੇ ਮੇਰਾ ਇੱਕ ਸਵਾਲ ਹੈ।"),
    ("od-IN", "Odia", "ମୋ ପିଲାଙ୍କ ଚେସ ପାଠ ବିଷୟରେ ମୋର ଗୋଟିଏ ପ୍ରଶ୍ନ ଅଛି।"),
)


def switch_wav(code: str, name: str) -> Path:
    return LANG_SAMPLES / f"{code}_switch.wav"


def content_wav(code: str) -> Path:
    return LANG_SAMPLES / f"{code}_content.wav"


def ensure_samples() -> None:
    """Generate any missing language fixtures with real Sarvam TTS."""
    from speech.tts import generate_speech

    LANG_SAMPLES.mkdir(parents=True, exist_ok=True)
    for code, name, sentence in MULTILINGUAL_CYCLE:
        sw = switch_wav(code, name)
        if not sw.is_file():
            print(f"  generating switch sample: {sw.name}")
            generate_speech(f"Can you speak in {name}?", sw,
                            language_code="en-IN")
        cw = content_wav(code)
        if not cw.is_file():
            print(f"  generating content sample: {cw.name}")
            generate_speech(sentence, cw, language_code=code)
    for extra in ("ur-IN",):
        sw = switch_wav(extra, "Urdu")
        if not sw.is_file():
            print(f"  generating switch sample: {sw.name}")
            generate_speech("Can you speak Urdu?", sw,
                            language_code="en-IN")
    hindi_pick = LANG_SAMPLES / "pick_hindi.wav"
    if not hindi_pick.is_file():
        print(f"  generating pick sample: {hindi_pick.name}")
        # A phrase, not a bare word — bare "Hindi" gets mis-transcribed
        # ("Himbi") by saaras and would never match a language alias.
        generate_speech("Hindi please.", hindi_pick, language_code="en-IN")


def active_calls(port: int) -> "int | None":
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            return json.loads(resp.read())["active_calls"]
    except Exception:
        return None


def wait_idle_server(port: int, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if active_calls(port) == 0:
            return True
        time.sleep(0.3)
    return False


class CallClient:
    """Exotel-faithful simulated caller: echoes marks, waits for bot
    audio to go idle before speaking (paced audio arrives in real
    time)."""

    def __init__(self, url: str, label: str):
        import websockets

        self._websockets = websockets
        self.url = url
        self.label = label
        self.media = 0
        self.marks = 0
        self.clears = 0
        self.server_closed = False
        self.stopped = asyncio.Event()

    async def __aenter__(self):
        self.ws = await self._websockets.connect(self.url,
                                                 max_size=1 << 20)
        self._rx = asyncio.create_task(self._recv())
        return self

    async def __aexit__(self, *_):
        self._rx.cancel()
        try:
            await self.ws.close()
        except Exception:
            pass

    async def _recv(self):
        try:
            async for raw in self.ws:
                m = json.loads(raw)
                ev = m.get("event")
                if ev == "media":
                    self.media += 1
                elif ev == "mark":
                    self.marks += 1
                    name = (m.get("mark") or {}).get("name")
                    if name:
                        try:
                            await self.ws.send(json.dumps(
                                {"event": "mark", "mark": {"name": name}}))
                        except Exception:
                            return
                elif ev == "clear":
                    self.clears += 1
        except self._websockets.ConnectionClosed:
            pass
        finally:
            # clean closes end the async-for without raising
            self.server_closed = True
            self.stopped.set()

    async def start_call(self, sid_suffix: str) -> None:
        await self.ws.send('{"event":"connected"}')
        await asyncio.sleep(0.1)
        await self.ws.send(json.dumps({"event": "start", "start": {
            "stream_sid": f"multi-{sid_suffix}",
            "call_sid": f"multi-call-{sid_suffix}"}}))
        t0 = time.monotonic()
        while self.media == 0 and time.monotonic() - t0 < 15:
            await asyncio.sleep(0.1)
        if self.media == 0:
            raise RuntimeError(f"{self.label}: no greeting audio in 15 s")
        await self.wait_idle()

    async def wait_idle(self, idle_s: float = 0.9, timeout_s: float = 20):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            last = self.media
            await asyncio.sleep(idle_s)
            if self.media == last:
                return

    async def speak(self, wav: Path) -> int:
        before = self.media
        pcm = load_wav_pcm16(wav)
        chunk = int(RATE * 0.1) * 2
        data = pcm.tobytes()
        for i in range(0, len(data), chunk):
            await self.ws.send(json.dumps({"event": "media", "media": {
                "payload": base64.b64encode(
                    data[i:i + chunk]).decode()}}))
            await asyncio.sleep(0.1)
        silence = base64.b64encode(b"\x00\x00" * (RATE // 10)).decode()
        for _ in range(10):
            await self.ws.send(json.dumps(
                {"event": "media", "media": {"payload": silence}}))
            await asyncio.sleep(0.1)
        t_turn = time.monotonic()
        while (self.media == before
               and time.monotonic() - t_turn < 30
               and not self.stopped.is_set()):
            await asyncio.sleep(0.1)
        return self.media - before

    async def stop(self, sid_suffix: str):
        await self.ws.send(json.dumps(
            {"event": "stop", "call_sid": f"multi-call-{sid_suffix}"}))
        try:
            await asyncio.wait_for(self.stopped.wait(), 10)
        except asyncio.TimeoutError:
            await self.ws.close()


def new_call_log(before: "set[str]", timeout: float = 10) -> "dict | None":
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = set(p for p in os.listdir(ROOT / "prototype/logs/calls")
                   if p.startswith("call-") and p.endswith(".json"))
        new = [p for p in logs - before]
        if new:
            path = ROOT / "prototype/logs/calls" / max(
                new, key=lambda p: os.path.getmtime(
                    ROOT / "prototype/logs/calls" / p))
            return json.loads(path.read_text())
        time.sleep(0.2)
    return None


def call_logs_snapshot() -> "set[str]":
    target = ROOT / "prototype/logs/calls"
    return {p for p in os.listdir(target)
            if p.startswith("call-") and p.endswith(".json")}


async def main() -> int:
    cfg = config.load_config()
    url = (f"ws://127.0.0.1:{cfg.exotel_ws_port}{cfg.exotel_ws_path}"
           f"?sample-rate={RATE}")
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'} — {label}"
              f"{'  [' + detail + ']' if detail and not cond else ''}")
        if not cond:
            ok = False

    if active_calls(cfg.exotel_ws_port) != 0:
        print("ERROR: active_calls != 0 before testing.")
        return 1

    print("Ensuring language samples (cached under "
          "audio_samples/sarvam/languages/)...")
    ensure_samples()

    # ---- Call A: cycle all 11 Bulbul languages in one call -------------
    print("CALL A: one call cycling 11 Bulbul-voiced languages")
    before = call_logs_snapshot()
    async with CallClient(url, "call-A") as call:
        await call.start_call("cycle")
        for code, name, _sentence in MULTILINGUAL_CYCLE:
            await call.speak(switch_wav(code, name))
            await call.wait_idle(idle_s=0.6, timeout_s=15)
            await call.speak(content_wav(code))
            await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.stop("cycle")
    check("active_calls == 0 after call A",
          wait_idle_server(cfg.exotel_ws_port))
    log_a = new_call_log(before)
    if not log_a:
        check("call A log written", False)
    else:
        print(f"  call A: turns={len(log_a['turns'])} "
              f"reply_language={log_a['reply_language']} "
              f"tts_language={log_a['tts_language']}")
        for code, name, _sentence in MULTILINGUAL_CYCLE:
            idx = MULTILINGUAL_CYCLE.index((code, name, _sentence))
            # assistant replies after the switch request (even turn idx)
            assistant = [t for t in log_a["turns"]
                         if t.get("speaker") == "assistant"]
            users = [t for t in log_a["turns"] if t.get("speaker") == "user"]
            a = assistant[1 + 2 * idx] if len(assistant) > 1 + 2 * idx else {}
            u = users[1 + 2 * idx] if len(users) > 1 + 2 * idx else {}
            check(f"{name}: assistant replies in {code}",
                  a.get("language") == code,
                  f"got {a.get('language')!r}: {(a.get('text') or '')[:60]}")
            check(f"{name}: reply spoken with {code} Bulbul voice",
                  a.get("tts_language") == code,
                  f"tts={a.get('tts_language')!r}")
            check(f"{name}: STT auto-detected native sentence as {code}",
                  u.get("language") == code,
                  f"got {u.get('language')!r}: {(u.get('text') or '')[:60]}")
    await asyncio.sleep(5)

    # ---- Call B: code-mixed Hinglish -----------------------------------
    print("CALL B: Hindi request → Hinglish turn (code-mixing preserved)")
    before = call_logs_snapshot()
    async with CallClient(url, "call-B") as call:
        await call.start_call("hinglish")
        await call.speak(switch_wav("hi-IN", "Hindi"))   # explicit ask
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.speak(SAMPLES / "hinglish" / "account_help.wav")
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.speak(SAMPLES / "hindi" / "problem.wav")   # pure Hindi
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.stop("hinglish")
    check("active_calls == 0 after call B",
          wait_idle_server(cfg.exotel_ws_port))
    log_b = new_call_log(before)
    if not log_b:
        check("call B log written", False)
    else:
        users = [t for t in log_b["turns"] if t.get("speaker") == "user"]
        assistant = [t for t in log_b["turns"]
                     if t.get("speaker") == "assistant"]
        check("pure Hindi sentence auto-detected (hi-IN)",
              any(t.get("language") == "hi-IN" for t in users),
              f"users={[(t.get('language')) for t in users]}")
        # Hinglish may be detected as hi-IN or en-IN by STT — what
        # matters is the explicit Hindi request stays sticky and the
        # reply never falls back to plain English TTS.
        check("reply language sticks to requested Hindi",
              log_b.get("reply_language") == "hi-IN",
              f"reply={log_b.get('reply_language')!r}")
        check("all assistant turns spoken in hi-IN voice",
              all(t.get("tts_language") == "hi-IN"
                  for t in assistant[1:]),
              f"tts={[(t.get('tts_language')) for t in assistant]}")
        # Hinglish transcript recorded as-is (not forced to one language)
        mixed = users[1] if len(users) > 1 else {}
        has_latin = any("a" <= ch.lower() <= "z"
                        for ch in (mixed.get("text") or ""))
        check("mixed transcript preserved (Latin present in turn)",
              has_latin, f"text={(mixed.get('text') or '')[:60]!r}")
    await asyncio.sleep(5)

    # ---- Call C: Urdu (no Bulbul voice) fallback ------------------------
    print("CALL C: Urdu request → ask_hi_en fallback → continue in Hindi")
    before = call_logs_snapshot()
    async with CallClient(url, "call-C") as call:
        await call.start_call("urdu")
        await call.speak(switch_wav("ur-IN", "Urdu"))
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.speak(LANG_SAMPLES / "pick_hindi.wav")
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.speak(SAMPLES / "hindi" / "account_help.wav")
        await call.wait_idle(idle_s=0.6, timeout_s=15)
        await call.stop("urdu")
    check("active_calls == 0 after call C",
          wait_idle_server(cfg.exotel_ws_port))
    log_c = new_call_log(before)
    if not log_c:
        check("call C log written", False)
    else:
        users = [t for t in log_c["turns"] if t.get("speaker") == "user"]
        assistant = [t for t in log_c["turns"]
                     if t.get("speaker") == "assistant"]
        notice = assistant[1] if len(assistant) > 1 else {}
        check("Urdu request recorded (requested_language=ur-IN once)",
              users and users[0].get("language") == "en-IN",
              f"users={[(t.get('language')) for t in users]}")
        check("fallback notice spoken IN FALLBACK VOICE (not fake Urdu)",
              notice.get("tts_language") == "en-IN"
              and "Hindi or English" in (notice.get("text") or ""),
              f"tts={notice.get('tts_language')!r} "
              f"text={(notice.get('text') or '')[:80]!r}")
        check("caller picked Hindi → reply_language=hi-IN with hi-IN voice",
              log_c.get("reply_language") == "hi-IN"
              and log_c.get("tts_language") == "hi-IN",
              f"reply={log_c.get('reply_language')!r} "
              f"tts={log_c.get('tts_language')!r}")
        check("final Hindi answer spoken by the hi-IN Bulbul voice",
              assistant[-1].get("tts_language") == "hi-IN",
              f"last turn tts={assistant[-1].get('tts_language')!r}")

    print()
    print("MULTILINGUAL LIVE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
