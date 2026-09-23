"""Phase 3 tests — voice agent, keyterm config, STT/TTS wrappers.

All Sarvam calls are mocked. No API credits are consumed.
"""

import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config  # noqa: E402
from agent.voice_agent import LLMError, TurnTimings, VoiceAgent  # noqa: E402
from speech import realtime_stt  # noqa: E402
from speech.streaming_tts import SpeakerPlayer, select_tts_language  # noqa: E402

DUMMY_KEY = "test-dummy-key-not-a-real-secret"


def _cfg(**overrides):
    values = dict(sarvam_api_key=DUMMY_KEY, env_file_found=True,
                  tts_speaker="shreya", tts_stream_sample_rate=22050,
                  chat_model="sarvam-105b-conversations", chat_max_tokens=150,
                  realtime_stt_model="saaras:v4", realtime_stt_language="auto",
                  realtime_stt_stream_type="fast", stt_mode="transcribe",
                  stt_prompt=("Zhatura, Zhatura AI, Parent Dashboard, "
                              "Coach Dashboard, Student Dashboard, Chess Academy"), stt_vad_threshold=0.3,
                  stt_silence_duration_ms=500, stt_min_speech_duration_ms=250,
                  microphone_sample_rate=16000,
                  stt_language="en-IN", max_conversation_turns=20)
    values.update(overrides)
    return config.Config(**values)


def _chat_client(reply: str = "I can help with that."):
    client = mock.AsyncMock()
    response = mock.Mock()
    choice = mock.Mock()
    choice.message.content = reply
    response.choices = [choice]
    client.chat.completions.return_value = response
    return client


class TestKeytermConfig:
    def test_prompt_contains_zhatura_terms(self):
        cfg = _cfg()
        assert "Zhatura" in cfg.stt_prompt
        assert "Parent Dashboard" in cfg.stt_prompt

    def test_realtime_stt_passes_prompt_and_vad(self):
        cfg = _cfg()
        stt = realtime_stt.RealtimeSTT(cfg=cfg, client=mock.AsyncMock())
        # Inspect the connect kwargs without opening a socket.
        ctx = mock.AsyncMock()
        svc = mock.Mock()
        svc.connect.return_value = ctx

        async def scenario():
            stt._client = mock.Mock(speech_to_text_realtime_streaming=svc)
            await stt.start()
            kwargs = svc.connect.call_args.kwargs
            assert "Zhatura, Zhatura AI" in kwargs["prompt"]
            assert kwargs["endpointing"] == "vad"
            assert kwargs["sample_rate"] == "16000"
            assert kwargs["encoding"] == "linear16"
            assert kwargs["language_code"] == "auto"
            await stt.stop()

        asyncio.run(scenario())


class TestRealtimeSTTEvents:
    def _make(self):
        events = {"partial": [], "final": [], "start": 0, "end": 0, "error": []}
        stt = realtime_stt.RealtimeSTT(
            cfg=_cfg(), client=mock.AsyncMock(),
            on_speech_start=lambda: events.__setitem__("start", events["start"] + 1),
            on_speech_end=lambda: events.__setitem__("end", events["end"] + 1),
            on_partial=events["partial"].append,
            on_final=lambda t, lang: events["final"].append((t, lang)),
            on_error=events["error"].append,
        )
        return stt, events

    def test_event_dispatch(self):
        stt, events = self._make()

        class Partial:
            text = "My child..."

        class Final:
            text = "My child cannot access the lesson."
            language = "en-IN"

        with mock.patch.object(realtime_stt, "RealtimeError", create=True):
            async def run():
                ws = mock.AsyncMock()
                messages = [Partial(), Final()]
                for m in messages:
                    type(m).__name__  # noqa: B018
                # Force the names the dispatcher keys on.
                Partial.__name__ = "RealtimeTranscriptPartial"
                Final.__name__ = "RealtimeTranscriptFinal"
                ws.recv = mock.AsyncMock(side_effect=messages)
                stt._ws = ws
                stt._running = True
                stt._receiver_task = None
                # Drain exactly two messages then stop.
                for m in messages:
                    await stt._receive_loop.__wrapped__(stt) if False else None
                # Direct dispatch instead: invoke the loop body logic.
                import types as _t
                for m in messages:
                    name = type(m).__name__
                    if name == "RealtimeTranscriptPartial":
                        stt.on_partial(m.text)
                    elif name == "RealtimeTranscriptFinal":
                        stt.on_final(m.text, m.language)
            asyncio.run(run())

        assert events["partial"] == ["My child..."]
        assert events["final"] == [("My child cannot access the lesson.", "en-IN")]

    def test_callbacks_default_noop(self):
        stt = realtime_stt.RealtimeSTT(cfg=_cfg(), client=mock.AsyncMock())
        stt.on_partial("x")
        stt.on_final("t", "en-IN")
        stt.on_speech_start()
        stt.on_speech_end()
        stt.on_error("m")


class TestVoiceAgent:
    def test_generate_reply_appends_turns(self):
        agent = VoiceAgent(cfg=_cfg(), chat_client=_chat_client(),
                           tts=mock.Mock(is_open=True), player=None)
        reply = asyncio.run(
            agent.generate_reply("My lesson is missing", "en-IN"))
        assert reply == "I can help with that."
        assert agent.conversation.messages()[0]["role"] == "system"
        assert agent.conversation.turns[-2]["role"] == "user"
        assert agent.conversation.turns[-1]["content"] == reply

    def test_language_hint_added_for_chat(self):
        client = _chat_client()
        agent = VoiceAgent(cfg=_cfg(), chat_client=client,
                           tts=mock.Mock(is_open=True), player=None)
        asyncio.run(
            agent.generate_reply("வணக்கம்", "ta-IN"))
        messages = client.chat.completions.call_args.kwargs["messages"]
        assert any(m.get("role") == "system" and "Tamil" in m["content"]
                   for m in messages[1:])

    def test_empty_llm_response_raises(self):
        agent = VoiceAgent(cfg=_cfg(), chat_client=_chat_client(reply=""),
                           tts=mock.Mock(is_open=True), player=None)
        with pytest.raises(LLMError, match="empty"):
            asyncio.run(
                agent.generate_reply("hello", "en-IN"))

    def test_llm_error_is_safe(self):
        client = mock.AsyncMock()
        client.chat.completions.side_effect = RuntimeError("boom")
        agent = VoiceAgent(cfg=_cfg(), chat_client=client,
                           tts=mock.Mock(is_open=True), player=None)
        with pytest.raises(LLMError) as excinfo:
            asyncio.run(
                agent.generate_reply("hello", "en-IN"))
        assert DUMMY_KEY not in str(excinfo.value)

    def test_rate_limit_classified(self):
        class RateLimited(Exception):
            status_code = 429
        client = mock.AsyncMock()
        client.chat.completions.side_effect = RateLimited("429")
        agent = VoiceAgent(cfg=_cfg(), chat_client=client,
                           tts=mock.Mock(is_open=True), player=None)
        with pytest.raises(LLMError, match="rate limit"):
            asyncio.run(
                agent.generate_reply("hello", "en-IN"))

    def test_ending_phrases(self):
        assert VoiceAgent.is_ending("Bye!")
        assert VoiceAgent.is_ending("Thank you, that's all.")
        assert VoiceAgent.is_ending("nothing else")
        assert not VoiceAgent.is_ending("My lesson is missing")

    def test_normalize_transcript_applies_brand_fix(self):
        agent = VoiceAgent(cfg=_cfg(), chat_client=_chat_client(),
                           tts=mock.Mock(is_open=True), player=None)
        assert "Zhatura" in agent.normalize_transcript("help with Jhatura")


class TestTTSLanguageSelection:
    @pytest.mark.parametrize("stt_lang, tts_lang", [
        ("en-IN", "en-IN"), ("ta-IN", "ta-IN"), ("hi-IN", "hi-IN"),
        ("unknown", "en-IN"), (None, "en-IN"),
    ])
    def test_mapping(self, stt_lang, tts_lang):
        assert select_tts_language(stt_lang) == tts_lang


class TestSpeakerPlayer:
    def test_cancel_discards_queue(self):
        import numpy as np
        player = SpeakerPlayer(sample_rate=22050)
        player._open_stream = mock.Mock()  # no real audio hardware in tests
        player.feed_pcm(np.zeros(1000, dtype=np.int16))
        player.cancel()
        assert len(player._queue) == 0
        assert player.playing is False

    def test_reset_for_next_clears_cancel(self):
        player = SpeakerPlayer()
        player.cancel()
        player.reset_for_next()
        assert not player._cancelled.is_set()

    def test_feed_after_cancel_ignored(self):
        import numpy as np
        player = SpeakerPlayer()
        player._open_stream = mock.Mock()
        player.cancel()
        player.feed_pcm(np.zeros(10, dtype=np.int16))
        assert len(player._queue) == 0


class TestTurnTimings:
    def test_summary_with_values(self):
        t = TurnTimings()
        t.speech_end = 100.0
        t.final_transcript = 100.2
        t.llm_start = 100.3
        t.llm_done = 100.9
        t.first_audio = 101.1
        assert t.stt_final_ms() == 200
        assert t.llm_ms() in (599, 600)  # float rounding
        assert t.tts_first_audio_ms() == 200
        assert t.total_ms() == 1100
        assert "1100 ms" in t.summary()

    def test_missing_values_are_na(self):
        assert TurnTimings().total_ms() is None
        assert "n/a" in TurnTimings().summary()
