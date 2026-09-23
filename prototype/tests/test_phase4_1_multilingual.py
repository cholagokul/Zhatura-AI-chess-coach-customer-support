"""Phase 4.1 tests — Sarvam multilingual expansion.

Centralized language registry, alias-based explicit switching across all
scheduled STT languages, TTS capability routing with the ask_hi_en
fallback, per-call language isolation. All mock-only: no Sarvam
credits, no Exotel, no ngrok.
"""

import asyncio
import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from agent.languages import (  # noqa: E402
    LANGUAGES,
    STT_SUPPORTED_CODES,
    TTS_SUPPORTED_CODES,
    TTS_UNSUPPORTED_CODES,
    get_language,
    language_name,
    match_language_alias,
    normalize_language_code,
    supports_stt,
    supports_tts,
)
from agent.state import AgentState  # noqa: E402
from agent.voice_agent import detect_language_switch  # noqa: E402
from speech.streaming_tts import TTS_LANGUAGES  # noqa: E402

from tests.test_phase4_exotel import (  # noqa: E402
    FakeTTS as _FakeTTSRef,  # noqa: F401  (documents the fake contract)
    _cfg,
    _make_session,
)

# The spec's authoritative language list (all scheduled Sarvam STT
# languages). Odia's Sarvam API code is od-IN (ISO 639-3).
ALL_STT_CODES = (
    "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "pa-IN", "od-IN",
    "as-IN", "ur-IN", "ne-IN", "kok-IN", "ks-IN", "sd-IN", "sa-IN",
    "sat-IN", "mni-IN", "brx-IN", "mai-IN", "doi-IN",
)

BULBUL_TTS_CODES = (
    "en-IN", "hi-IN", "bn-IN", "ta-IN", "te-IN", "kn-IN", "ml-IN",
    "mr-IN", "gu-IN", "pa-IN", "od-IN",
)


class TestLanguageRegistry:
    def test_all_spec_stt_languages_present_and_supported(self):
        assert set(STT_SUPPORTED_CODES) == set(ALL_STT_CODES)
        for code in ALL_STT_CODES:
            assert supports_stt(code), code

    def test_exactly_the_eleven_bulbul_languages_have_tts(self):
        assert tuple(sorted(TTS_SUPPORTED_CODES)) == \
            tuple(sorted(BULBUL_TTS_CODES))
        assert set(TTS_LANGUAGES) == set(BULBUL_TTS_CODES)

    def test_unsupported_tts_languages_exact(self):
        assert set(TTS_UNSUPPORTED_CODES) == {
            "as-IN", "ur-IN", "ne-IN", "kok-IN", "ks-IN", "sd-IN",
            "sa-IN", "sat-IN", "mni-IN", "brx-IN", "mai-IN", "doi-IN",
        }
        for code in TTS_UNSUPPORTED_CODES:
            assert supports_stt(code)
            assert not supports_tts(code)

    def test_every_language_has_name_native_and_aliases_shape(self):
        for language in LANGUAGES:
            assert language.name
            assert language.native_name
            assert language_name(language.code) == language.name

    def test_odia_historical_code_normalizes(self):
        assert normalize_language_code("or-IN") == "od-IN"
        assert get_language("or-IN").name == "Odia"
        assert supports_tts("or-IN")  # alias → od-IN → Bulbul voice


class TestAliasDetection:
    @pytest.mark.parametrize("text,code", [
        ("Tamil", "ta-IN"), ("தமிழ்", "ta-IN"), ("tamizh", "ta-IN"),
        ("Hindi", "hi-IN"), ("हिंदी", "hi-IN"),
        ("Bengali", "bn-IN"), ("Bangla", "bn-IN"), ("বাংলা", "bn-IN"),
        ("Telugu", "te-IN"), ("తెలుగు", "te-IN"),
        ("Kannada", "kn-IN"), ("ಕನ್ನಡ", "kn-IN"),
        ("Malayalam", "ml-IN"), ("മലയാളം", "ml-IN"),
        ("Marathi", "mr-IN"), ("मराठी", "mr-IN"),
        ("Gujarati", "gu-IN"), ("ગુજરાતી", "gu-IN"),
        ("Punjabi", "pa-IN"), ("ਪੰਜਾਬੀ", "pa-IN"),
        ("Odia", "od-IN"), ("oriya", "od-IN"),
        ("Urdu", "ur-IN"), ("Nepali", "ne-IN"), ("Sanskrit", "sa-IN"),
        ("Konkani", "kok-IN"), ("Kashmiri", "ks-IN"),
        ("Santali", "sat-IN"), ("meitei", "mni-IN"),
        ("Bodo", "brx-IN"), ("Maithili", "mai-IN"), ("Dogri", "doi-IN"),
        ("Assamese", "as-IN"),
    ])
    def test_alias_mentions(self, text, code):
        assert match_language_alias(text) == code

    def test_no_language_mention(self):
        assert match_language_alias("please help me with my account") is None


class TestExplicitSwitching:
    """Spec §2 examples, extended to every registry language."""

    @pytest.mark.parametrize("text,code", [
        ("Speak Tamil", "ta-IN"),
        ("Can you speak Bengali?", "bn-IN"),
        ("Please continue in Telugu", "te-IN"),
        ("Kannada please", "kn-IN"),
        ("Hindi mein baat karo", "hi-IN"),
        ("Can you speak in Tamil?", "ta-IN"),
        ("Can we switch to Bangla?", "bn-IN"),
        ("Please speak Malayalam", "ml-IN"),
        ("Can you speak Marathi?", "mr-IN"),
        ("Please continue in Gujarati", "gu-IN"),
        ("Punjabi please", "pa-IN"),
        ("Can you speak Odia?", "od-IN"),
        ("Please switch to Urdu", "ur-IN"),
        ("Can you speak Nepali?", "ne-IN"),
        ("Please continue in Sanskrit", "sa-IN"),
        ("Can you speak Bodo?", "brx-IN"),
        ("தமிழில் பேச முடியுமா?", "ta-IN"),
        ("Can you switch back to English?", "en-IN"),
    ])
    def test_switch_requests_detected(self, text, code):
        assert detect_language_switch(text) == code

    @pytest.mark.parametrize("text", [
        "I am learning Tamil on Zhatura.",
        "Do you have Tamil chess lessons?",
        "My son studies in a Hindi medium school.",
        "The English course is good.",
        "Can you help me with my account",
        "What are the Bengali plan options?",   # mention, not a request
    ])
    def test_no_false_switches(self, text):
        assert detect_language_switch(text) is None


def _fresh_session(monkeypatch, tmp_path):
    from tests.test_phase4_exotel import FakeWebSocket
    return _make_session(monkeypatch, FakeWebSocket(), tmp_path)


class TestSessionLanguageState:
    def test_auto_detection_updates_detected_language(self, monkeypatch,
                                                      tmp_path):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                s._on_final("Hello, I need help", "en-IN")
                assert s.detected_language == "en-IN"
                assert s.reply_language == "en-IN"
                s._on_final("নমস্কার, সাহায্য দরকার", "bn-IN")
                assert s.detected_language == "bn-IN"
                assert s.requested_language == ""
                assert s.reply_language == "bn-IN"
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    @pytest.mark.parametrize("utterance,code", [
        ("Can you speak in Tamil?", "ta-IN"),
        ("Can you speak Bengali?", "bn-IN"),
        ("Please continue in Telugu", "te-IN"),
        ("Kannada please", "kn-IN"),
        ("Hindi mein baat karo", "hi-IN"),
    ])
    def test_explicit_switch_sets_language_state(self, monkeypatch,
                                                 tmp_path, utterance, code):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                s._on_final(utterance, "en-IN")
                assert s.requested_language == code
                assert s.reply_language == code
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    def test_tamil_to_english_switch_back(self, monkeypatch, tmp_path):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                s._on_final("Can you speak in Tamil?", "en-IN")
                assert s.reply_language == "ta-IN"
                # caller speaks Tamil; sticky request keeps replying Tamil
                s._on_final("தயவுசெய்து தொடரவும்", "ta-IN")
                assert s.reply_language == "ta-IN"
                # explicit switch back
                s._on_final("Can you switch back to English?", "en-IN")
                assert s.requested_language == "en-IN"
                assert s.reply_language == "en-IN"
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    def test_code_mixed_turn_keeps_requested_language(self, monkeypatch,
                                                      tmp_path):
        """Hinglish turn (STT detects hi-IN or en-IN) must not yank the
        reply language away from an explicit Tamil request."""
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                s._on_final("Please continue in Tamil", "en-IN")
                # Tanglish sentence — saaras often reports "en-IN" for it
                s._on_final("Enakku oru question iruku about my account",
                            "en-IN")
                assert s.detected_language == "en-IN"   # honest detection
                assert s.reply_language == "ta-IN"      # reply stays Tamil
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    def test_per_call_language_isolation(self, monkeypatch, tmp_path):
        async def scenario():
            s1 = _fresh_session(monkeypatch, tmp_path)
            s2 = _fresh_session(monkeypatch, tmp_path)
            try:
                s1._on_final("Can you speak in Tamil?", "en-IN")
                s1._on_final("தமிழில் தொடரவும்", "ta-IN")
                assert s1.reply_language == "ta-IN"
                assert s2.detected_language == ""
                assert s2.reply_language == "en-IN"
                assert s2.requested_language == ""
            finally:
                await s1.shutdown()
                await s2.shutdown()
        asyncio.run(scenario())


class TestReplyLanguageToLLM:
    @pytest.mark.parametrize("utterance,code,name", [
        ("Please continue in Telugu", "te-IN", "Telugu"),
        ("Can you speak Bengali?", "bn-IN", "Bengali"),
        ("Can you speak in Tamil?", "ta-IN", "Tamil"),
        ("Kannada please", "kn-IN", "Kannada"),
    ])
    def test_llm_instructed_to_answer_in_language(self, monkeypatch,
                                                  tmp_path, utterance, code,
                                                  name):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                s._on_final(utterance, "en-IN")
                s.state.transition(AgentState.LISTENING)
                s.state.transition(AgentState.PROCESSING)
                from telephony import session as session_module
                await s._respond(utterance, "en-IN",
                                 session_module.TurnTimings())
                assert s.tts.last_language == code
                # the per-turn system hint names the reply language
                call = s.agent._client.chat.completions.call_args
                messages = call.kwargs["messages"]
                hint = messages[-1]["content"]
                assert f"Reply in {name} ({code})" in hint
            finally:
                await s.shutdown()
        asyncio.run(scenario())


class TestUnsupportedTTSFallback:
    def test_urdu_request_gets_ask_hi_en_fallback(self, monkeypatch,
                                                  tmp_path, caplog):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                with caplog.at_level("WARNING",
                                     logger="telephony.session"):
                    s._on_final("Can you speak Urdu?", "en-IN")
                    s.state.transition(AgentState.LISTENING)
                    s.state.transition(AgentState.PROCESSING)
                    from telephony import session as session_module
                    await s._respond("Can you speak Urdu?", "en-IN",
                                     session_module.TurnTimings())

                assert s.requested_language == "ur-IN"
                # spoken in the fallback voice, never in fake Urdu
                assert s.tts_language == s.cfg.tts_fallback_language == "en-IN"
                assert s.tts.last_language == "en-IN"
                notice = s.tts.spoken[-1]
                assert "Urdu" in notice and "Hindi or English" in notice
                assert s.reply_language == "en-IN"
                assert s._fallback_choice_pending is True
                assert "TTS_UNAVAILABLE_FOR_LANGUAGE: ur-IN" in caplog.text

                # STT/detection conversation state kept working
                assert s.detected_language == "en-IN"

                # caller answers the question with a bare language name
                s._on_final("Hindi", "hi-IN")
                assert s.requested_language == "hi-IN"
                assert s.reply_language == "hi-IN"
                assert s._fallback_choice_pending is False
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    def test_fallback_notice_logged_once_per_language_per_call(
            self, monkeypatch, tmp_path, caplog):
        async def scenario():
            s = _fresh_session(monkeypatch, tmp_path)
            try:
                with caplog.at_level("WARNING",
                                     logger="telephony.session"):
                    s._on_final("Can you speak Urdu?", "en-IN")
                    for _ in range(2):
                        s.state.transition(AgentState.LISTENING)
                        s.state.transition(AgentState.PROCESSING)
                        from telephony import session as session_module
                        # force the situation again after the first ask
                        s.requested_language = "ur-IN"
                        s.reply_language = "ur-IN"
                        await s._respond("Urdu pannunga", "en-IN",
                                         session_module.TurnTimings())
                assert caplog.text.count(
                    "TTS_UNAVAILABLE_FOR_LANGUAGE: ur-IN") == 1
            finally:
                await s.shutdown()
        asyncio.run(scenario())

    def test_supports_tts_is_the_single_router(self):
        # every Bulbul code routes through unchanged
        for code in BULBUL_TTS_CODES:
            assert supports_tts(code)
        # and nothing else does
        for code in TTS_UNSUPPORTED_CODES:
            assert not supports_tts(code)
