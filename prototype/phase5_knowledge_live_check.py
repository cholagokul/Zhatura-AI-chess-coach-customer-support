"""Phase 5 knowledge LIVE check — real Sarvam, simulated Exotel calls
against the DEV server on port 8001 (the live Phase 4 server on 8000
is never touched).

    Terminal A: EXOTEL_WEBSOCKET_PORT=8001 python prototype/phase4_exotel_server.py
    Terminal B: python prototype/phase5_knowledge_live_check.py

Call A (English): grounded product answers (Zhatura / AI Chess Coach /
parent dashboard), pricing guard ("What plans do you offer?" must say
verified details unavailable, never a number), account guard ("My child
cannot see today's lesson" must NOT claim account access), then a voice
end-call (bypass + hangup regression).

Call B (multilingual): Tamil switch → grounded Tamil answer, Hindi
switch → grounded Hindi answer, Telugu switch → grounded Telugu answer,
then Tanglish code-mixed question while Tamil is the sticky requested
language (Phase 4.1 behavior must survive).

Call C (barge-in regression): second question spoken while the first
grounded answer is still playing → clear event, old answer cancelled,
new answer spoken.

Question audio is generated with Bulbul v3 and cached under
audio_samples/sarvam/knowledge/ (first run only).

Exit 0 = all scenarios behaved as expected.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from phase4_live_call_check import load_wav_pcm16  # noqa: E402
from phase4_stabilization_live_check import (  # noqa: E402
    CallResult,
    run_call,
)

ROOT = Path(__file__).resolve().parent.parent
RATE = 16000
KNOW = ROOT / "audio_samples" / "sarvam" / "knowledge"
SAMPLES = ROOT / "audio_samples" / "sarvam"
DEV_PORT = int(os.environ.get("PHASE5_DEV_PORT", "8001"))

# question fixtures: (name, text, tts language)
QUESTIONS = (
    ("q_zhatura", "What is Zhatura?", "en-IN"),
    ("q_coach", "What does the Zhatura AI Chess Coach do?", "en-IN"),
    ("q_parent",
     "I am a parent. What can I see about my child's progress?",
     "en-IN"),
    ("q_plans", "What plans do you offer?", "en-IN"),
    ("q_child_lesson", "My child cannot see today's lesson.", "en-IN"),
    ("ta_zhatura", "ஜாத்துரா என்றால் என்ன?", "ta-IN"),
    ("hi_zhatura", "झतूरा क्या है?", "hi-IN"),
    ("te_coach", "ఝతురా AI చెస్ కోచ్ ఏమిటి?", "te-IN"),
    ("q_tanglish", "Parent dashboard la enna details irukum?", "ta-IN"),
)


def ensure_questions() -> None:
    from speech.tts import generate_speech

    KNOW.mkdir(parents=True, exist_ok=True)
    for name, text, lang in QUESTIONS:
        wav = KNOW / f"{name}.wav"
        if not wav.is_file():
            print(f"  generating question sample: {wav.name}")
            generate_speech(text, wav, language_code=lang)


def wait_idle_server(port: int, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health",
                         timeout=5) as resp:
                if json.loads(resp.read())["active_calls"] == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def new_call_log(before: "set[str]", timeout: float = 12) -> "dict | None":
    deadline = time.monotonic() + timeout
    target = ROOT / "prototype/logs/calls"
    while time.monotonic() < deadline:
        logs = {p for p in os.listdir(target)
                if p.startswith("call-") and p.endswith(".json")}
        new = [p for p in logs - before]
        if new:
            path = target / max(new, key=lambda p: os.path.getmtime(
                target / p))
            return json.loads(path.read_text())
        time.sleep(0.2)
    return None


def call_logs_snapshot() -> "set[str]":
    target = ROOT / "prototype/logs/calls"
    return {p for p in os.listdir(target)
            if p.startswith("call-") and p.endswith(".json")}


def assistant_after(log: dict, user_sub: str) -> "dict | None":
    """First assistant turn following the user turn containing
    ``user_sub`` (case-insensitive)."""
    turns = log.get("turns", [])
    for i, t in enumerate(turns):
        if t.get("speaker") == "user" and user_sub.lower() in (
                t.get("text") or "").lower():
            for later in turns[i + 1:]:
                if later.get("speaker") == "assistant":
                    return later
    return None


_PRICE_RE = re.compile(r"(?:₹|\$|€|\b\d[\d,\.]*\s*(?:rs\.?|inr|rupees?|"
                       r"dollars?|per month|per year|monthly|yearly)\b)",
                       re.IGNORECASE)
_TAMIL_RE = re.compile("[஀-௿]")
_DEVANAGARI_RE = re.compile("[ऀ-ॿ]")
_TELUGU_RE = re.compile("[ఀ-౿]")


async def main() -> int:
    cfg = config.load_config()
    url = (f"ws://127.0.0.1:{DEV_PORT}{cfg.exotel_ws_path}"
           f"?sample-rate={RATE}")
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'} — {label}"
              f"{'  [' + detail + ']' if detail and not cond else ''}")
        if not cond:
            ok = False

    print("Ensuring question samples (cached under "
          "audio_samples/sarvam/knowledge/)...")
    ensure_questions()

    # ---------------- Call A: grounded English + guards + end-call -----
    print("CALL A: grounded English answers + pricing/account guards + "
          "voice end-call")
    before = call_logs_snapshot()
    result_a = await run_call(
        "knowledge-A", url,
        [KNOW / "q_zhatura.wav", KNOW / "q_coach.wav",
         KNOW / "q_parent.wav", KNOW / "q_plans.wav",
         KNOW / "q_child_lesson.wav"],
        end_voice_wav=SAMPLES / "english" / "cut_the_call.wav")
    check("server closed WSS after voice end-call", result_a.server_closed)
    check("active_calls == 0 after call A", wait_idle_server(DEV_PORT))
    log_a = new_call_log(before)
    if not log_a:
        check("call A log written", False)
    else:
        check("disconnect_reason = user_end_phrase",
              log_a.get("disconnect_reason") == "user_end_phrase",
              f"got {log_a.get('disconnect_reason')!r}")

        a = assistant_after(log_a, "what is")
        check("Zhatura overview grounded (chess learning platform)",
              bool(a) and "chess" in (a["text"]).lower()
              and ("learning" in a["text"].lower()
                   or "platform" in a["text"].lower()),
              (a["text"][:100] if a else "no answer"))

        a = assistant_after(log_a, "chess coach")
        check("AI Chess Coach grounded",
              bool(a) and "coach" in a["text"].lower(),
              (a["text"][:100] if a else "no answer"))

        a = assistant_after(log_a, "progress")
        check("parent question → Parent Dashboard / progress grounded",
              bool(a) and ("dashboard" in a["text"].lower()
                           or "progress" in a["text"].lower()),
              (a["text"][:100] if a else "no answer"))

        a = assistant_after(log_a, "plans")
        plans_txt = (a["text"] if a else "").lower()
        check("plans question → honest 'not available' answer",
              bool(a) and ("verified" in plans_txt
                           or "not available" in plans_txt
                           or "don't have" in plans_txt),
              plans_txt[:100])
        check("plans answer contains NO price figure",
              bool(a) and not _PRICE_RE.search(a["text"]),
              (a["text"][:100] if a else ""))

        a = assistant_after(log_a, "lesson")
        child_txt = (a["text"] if a else "").lower()
        check("account question → admits no account access",
              bool(a) and "account" in child_txt and (
                  "can" in child_txt or "don't" in child_txt
                  or "unable" in child_txt or "not" in child_txt),
              child_txt[:100])
        check("account answer does NOT claim to have checked",
              bool(a) and "i checked" not in child_txt
              and "i can see your" not in child_txt
              and "your account shows" not in child_txt,
              child_txt[:100])
    await asyncio.sleep(5)

    # ---------------- Call B: multilingual grounded answers ------------
    print("CALL B: Tamil/Hindi/Telugu grounded answers + Tanglish "
          "code-mix")
    before = call_logs_snapshot()
    result_b = await run_call(
        "knowledge-B", url,
        [SAMPLES / "languages" / "ta-IN_switch.wav",
         KNOW / "ta_zhatura.wav",
         SAMPLES / "languages" / "hi-IN_switch.wav",
         KNOW / "hi_zhatura.wav",
         SAMPLES / "languages" / "te-IN_switch.wav",
         KNOW / "te_coach.wav",
         SAMPLES / "languages" / "ta-IN_switch.wav",
         KNOW / "q_tanglish.wav"])
    check("active_calls == 0 after call B", wait_idle_server(DEV_PORT))
    log_b = new_call_log(before)
    if not log_b:
        check("call B log written", False)
    else:
        ta_answers = [t for t in log_b["turns"]
                      if t.get("speaker") == "assistant"
                      and t.get("language") == "ta-IN"]
        hi_answers = [t for t in log_b["turns"]
                      if t.get("speaker") == "assistant"
                      and t.get("language") == "hi-IN"]
        te_answers = [t for t in log_b["turns"]
                      if t.get("speaker") == "assistant"
                      and t.get("language") == "te-IN"]
        check("Tamil grounded answer exists in Tamil script",
              any(_TAMIL_RE.search(t.get("text") or "") and (
                  "chess" in (t.get("text") or "").lower()
                  or "சதுரங்க" in (t.get("text") or ""))
                  for t in ta_answers),
              f"ta turns={[(t.get('text') or '')[:40] for t in ta_answers]}")
        check("Tamil answers spoken with ta-IN voice",
              bool(ta_answers) and all(
                  t.get("tts_language") == "ta-IN" for t in ta_answers))
        check("Hindi grounded answer exists in Devanagari",
              any(_DEVANAGARI_RE.search(t.get("text") or "")
                  for t in hi_answers),
              f"hi turns={[(t.get('text') or '')[:40] for t in hi_answers]}")
        check("Telugu grounded answer exists in Telugu script",
              any(_TELUGU_RE.search(t.get("text") or "")
                  for t in te_answers),
              f"te turns={[(t.get('text') or '')[:40] for t in te_answers]}")
        # saaras transcribes Tanglish in Tamil script ("டேஷ்போர்டில்"),
        # so match either script when locating the code-mixed turn.
        tanglish_user = [t for t in log_b["turns"]
                         if t.get("speaker") == "user"
                         and ("dashboard" in (t.get("text") or "").lower()
                              or "டேஷ்போர்ட" in (t.get("text") or "")
                              or "டாஷ்போர்ட" in (t.get("text") or ""))]
        follow = (assistant_after(log_b, tanglish_user[-1]["text"])
                  if tanglish_user else None)
        check("Tanglish question keeps sticky Tamil reply",
              bool(follow) and follow.get("language") == "ta-IN"
              and follow.get("tts_language") == "ta-IN",
              f"follow={(follow or {}).get('language')!r}")
    await asyncio.sleep(5)

    # ---------------- Call C: barge-in regression ----------------------
    print("CALL C: barge-in during a grounded answer")
    before = call_logs_snapshot()
    result_c = await run_call(
        "knowledge-C", url,
        [KNOW / "q_parent.wav", KNOW / "q_plans.wav"],
        barge_in_at_reply=True)
    check("clear event sent on barge-in", result_c.clears >= 1,
          f"clears={result_c.clears}")
    check("active_calls == 0 after call C", wait_idle_server(DEV_PORT))
    log_c = new_call_log(before)
    if not log_c:
        check("call C log written", False)
    else:
        assistants = [t for t in log_c["turns"]
                      if t.get("speaker") == "assistant"]
        check("final answer addresses the LATEST question (plans)",
              bool(assistants) and any(
                  w in (assistants[-1].get("text") or "").lower()
                  for w in ("plan", "price", "verified", "available")),
              (assistants[-1].get("text") or "")[:100] if assistants
              else "none")

    print()
    print("PHASE 5 KNOWLEDGE LIVE CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
