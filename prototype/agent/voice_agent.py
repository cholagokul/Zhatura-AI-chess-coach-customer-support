"""Zhatura AI Customer Care — voice agent orchestrator (Phase 3).

    final transcript → append user turn → Sarvam chat → assistant reply
                     → append assistant turn → streaming TTS → speaker

Transport (microphone/speaker) lives in prototype/speech/; this module
is transport-agnostic so Exotel telephony can replace local audio in a
later phase without rewriting the AI logic.

Never logs credentials or secrets.
"""

from __future__ import annotations

import asyncio
import logging
import time

try:
    from .. import config as _config_module
    from .brand_correction import correct_brand_terms, matches_spoken_echo
    from .conversation import Conversation
    from .languages import (  # noqa: F401  (LANGUAGE_NAMES re-exported)
        LANGUAGE_NAMES,
        match_language_alias,
    )
    from ..speech.streaming_tts import (
        SpeakerPlayer,
        StreamingTTS,
        StreamingTTSError,
        select_tts_language,
    )
    from ..tools.service import SupportToolService
    from ..tools.intents import SupportIntent, detect_support_intent, extract_identifiers
    from ..tools.grounding import (
        format_tool_result_context,
        format_verification_required_context,
        format_confirmation_required_context,
        format_permission_denied_context,
        format_backend_unavailable_context,
    )
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import config as _config_module
    from agent.brand_correction import correct_brand_terms, matches_spoken_echo
    from agent.conversation import Conversation
    from agent.languages import (  # noqa: F401
        LANGUAGE_NAMES,
        match_language_alias,
    )
    from speech.streaming_tts import (
        SpeakerPlayer,
        StreamingTTS,
        StreamingTTSError,
        select_tts_language,
    )
    from tools.service import SupportToolService
    from tools.intents import SupportIntent, detect_support_intent, extract_identifiers
    from tools.grounding import (
        format_tool_result_context,
        format_verification_required_context,
        format_confirmation_required_context,
        format_permission_denied_context,
        format_backend_unavailable_context,
    )

logger = logging.getLogger(__name__)

END_PHRASES = (
    "bye", "goodbye", "good bye", "thank you, that's all",
    "that's all", "nothing else", "end call", "end the call",
    "hang up", "hangup", "cut the call", "cut this call", "cut call",
    "cut the phone", "disconnect the call", "you can disconnect",
    "please disconnect", "cut pannunga", "call cut pannunga",
    "call-a cut pannunga", "phone-a cut pannunga", "call cut pannu",
)
CLOSING_TEXT = "Thank you for contacting Zhatura. Have a great day."
SILENCE_PROMPT_TEXT = "Are you still there?"

# Deterministic language-switch intents. Voice on the phone makes the
# LLM unreliable for this decision ("I can only speak in English"), so
# explicit requests are matched here and become session language state.
# Language names/aliases/natives come from agent/languages.py (all 23
# scheduled Sarvam STT languages); a request needs both the language
# mention AND a request verb/politeness token, so "I am learning Tamil"
# or "Kannada chess lessons" never trigger a switch.
_SWITCH_VERBS_LATIN = (
    "speak", "switch", "talk", "continue", "reply", "respond", "use",
    "change", "baat", "bolo", "pesu", "pesa", "pesunga", "pesanum",
    "baat karo", "baat karein", "speak in", "talk in", "can we",
    "please", "pls",
)
_SWITCH_VERBS_SCRIPT = ("பேச", "बात", "बोल")


def detect_language_switch(text: str) -> "str | None":
    """Return a language code when ``text`` explicitly asks to switch
    conversation language, else None.

    Deterministic on purpose: a language name alone ("I am learning
    Tamil") is NOT a switch request — a request verb or "please" must
    appear too ("Speak Tamil", "Kannada please", "Hindi mein baat karo",
    "தமிழில் பேச முடியுமா?", …). Covers every registry language, not
    just English/Tamil/Hindi.
    """
    lowered = text.strip().lower()
    padded = f" {lowered} "
    has_request = (
        any(f" {verb} " in padded for verb in _SWITCH_VERBS_LATIN)
        or any(verb in lowered for verb in _SWITCH_VERBS_SCRIPT)
    )
    if not has_request:
        return None
    return match_language_alias(lowered)


class LLMError(Exception):
    """Chat-model call failed (safe message, no secrets)."""


class TurnTimings:
    """Per-turn latency measurements (actual, never fabricated)."""

    def __init__(self):
        self.speech_end: "float | None" = None
        self.final_transcript: "float | None" = None
        self.llm_start: "float | None" = None
        self.llm_done: "float | None" = None
        self.first_audio: "float | None" = None

    def stt_final_ms(self):
        if self.speech_end and self.final_transcript:
            return round((self.final_transcript - self.speech_end) * 1000)
        return None

    def llm_ms(self):
        if self.llm_start and self.llm_done:
            return round((self.llm_done - self.llm_start) * 1000)
        return None

    def tts_first_audio_ms(self):
        if self.llm_done and self.first_audio:
            return round((self.first_audio - self.llm_done) * 1000)
        return None

    def total_ms(self):
        if self.speech_end and self.first_audio:
            return round((self.first_audio - self.speech_end) * 1000)
        return None

    def summary(self) -> str:
        def f(v):
            return f"{v} ms" if v is not None else "n/a"
        return (
            f"STT final latency: {f(self.stt_final_ms())}\n"
            f"LLM latency: {f(self.llm_ms())}\n"
            f"TTS first audio: {f(self.tts_first_audio_ms())}\n"
            f"Total response latency: {f(self.total_ms())}"
        )


class VoiceAgent:
    """Final transcript → chat reply → spoken audio."""

    def __init__(self, cfg=None, conversation: "Conversation | None" = None,
                 chat_client=None, tts: "StreamingTTS | None" = None,
                 player: "SpeakerPlayer | None" = None,
                 knowledge=None,
                 tool_service=None):
        if cfg is None:
            cfg = _config_module.load_config()
        self.cfg = cfg
        if chat_client is None:
            from sarvamai import AsyncSarvamAI

            chat_client = AsyncSarvamAI(api_subscription_key=cfg.sarvam_api_key)
        self._client = chat_client
        self.conversation = conversation or Conversation.from_prompt_file(
            max_turns=cfg.max_conversation_turns
        )
        self.tts = tts or StreamingTTS(cfg=cfg, client=self._client)
        self.player = player
        # Phase 5: verified Zhatura knowledge. Opt-out via
        # KNOWLEDGE_ENABLED=false or knowledge=None with enabled=False.
        self.knowledge = knowledge
        if self.knowledge is None and getattr(cfg, "knowledge_enabled",
                                              False):
            try:
                from ..knowledge.service import KnowledgeService
            except ImportError:  # pragma: no cover
                from knowledge.service import KnowledgeService
            try:
                self.knowledge = KnowledgeService(
                    getattr(cfg, "knowledge_dir", "") or None)
                logger.info("Knowledge base loaded (%d chunks, topics: %s).",
                            len(self.knowledge.store),
                            ", ".join(self.knowledge.store.topics()))
            except Exception:
                logger.exception("Knowledge base failed to load — running "
                                 "without grounding.")
                self.knowledge = None

        # Phase 7: Real/Mock Account Tools & Support Actions
        self.tool_service = tool_service
        if self.tool_service is None and getattr(cfg, "support_backend_mode", "disabled") != "disabled":
            try:
                self.tool_service = SupportToolService(
                    backend_mode=cfg.support_backend_mode,
                    fixture_path=getattr(cfg, "accounts_fixture_path", "") or None,
                    allow_mock_verification=getattr(cfg, "mock_verification_enabled", True),
                )
                logger.info("SupportToolService loaded (backend_mode=%s).", cfg.support_backend_mode)
            except Exception:
                logger.exception("SupportToolService failed to initialize.")
                self.tool_service = None

        self.current_reply = ""   # for echo suppression heuristics
        self.timings = TurnTimings()

    # -- chat -----------------------------------------------------------

    async def generate_reply(self, user_text: str,
                             user_language: str = "en-IN",
                             reply_language: "str | None" = None) -> str:
        """Append user turn, call the chat model, append assistant turn.

        ``reply_language`` overrides ``user_language`` for the reply
        (explicit caller language-switch requests on the phone)."""
        self.conversation.add_user(user_text)
        messages = self.conversation.messages()
        target = reply_language or user_language
        language_name = LANGUAGE_NAMES.get(target, "English")

        # Phase 7 grounding: tools & support actions
        tool_context, is_tool_handled = await self._tool_context(user_text, target)
        if tool_context:
            messages = messages + [{"role": "system",
                                    "content": tool_context}]

        # Phase 5 grounding: product-specific turns get a verified-
        # knowledge system message; honesty guards (unknown/pricing/
        # account) arrive as mandatory instructions in the same block.
        # Trivial turns (greetings, thanks), explicit language-switch
        # requests and end-call phrases never trigger retrieval.
        knowledge_context = self._knowledge_context(user_text, target)
        if knowledge_context:
            messages = messages + [{"role": "system",
                                    "content": knowledge_context}]

        messages = messages + [{
            "role": "system",
            "content": (f"The user just spoke in "
                        f"{LANGUAGE_NAMES.get(user_language, 'English')} "
                        f"({user_language}). Reply in {language_name} "
                        f"({target}) — match this language exactly. "
                        "If the caller code-mixes (e.g. "
                        "Hinglish/Tanglish), keep the same natural "
                        "code-mixing; never translate it into plain "
                        "English. "
                        "Keep it short, 1–4 sentences, spoken style."),
        }]
        try:
            self.timings.llm_start = time.monotonic()
            response = await self._client.chat.completions(
                model=self.cfg.chat_model,
                messages=messages,
                max_tokens=self.cfg.chat_max_tokens,
                temperature=0.4,
            )
        except Exception as exc:
            raise LLMError(_safe_llm_error(exc)) from None

        try:
            reply = (response.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError):
            raise LLMError("Chat model returned an empty or unreadable response.") from None
        if not reply:
            raise LLMError("Chat model returned an empty or unreadable response.")

        self.conversation.add_assistant(reply)
        self.current_reply = reply
        self.timings.llm_done = time.monotonic()
        logger.info("LLM reply ready (%d words).", len(reply.split()))
        return reply

    # -- tools (Phase 7) -------------------------------------------------

    async def _tool_context(self, text: str, reply_language: str) -> tuple[str, bool]:
        """Phase 7: evaluate tool requirements, permissions, and grounding.

        Returns (system_instruction_context, handled_account_specific_flag).
        """
        if self.tool_service is None:
            return "", False
        if detect_language_switch(text) or self.is_ending(text):
            return "", False

        has_pending = self.tool_service.has_pending_action()
        intent = detect_support_intent(text, has_pending_confirmation=has_pending)

        # 1. Action Confirmation Handling (Write Actions)
        if has_pending:
            staged = self.tool_service.pending_action
            tool_name = staged["tool_name"] if staged else "action"
            if intent == SupportIntent.CONFIRMATION_YES:
                res = await self.tool_service.confirm_pending_action(True)
                if res:
                    return format_tool_result_context(tool_name, res, self.tool_service.caller, reply_language), True
            elif intent == SupportIntent.CONFIRMATION_NO:
                res = await self.tool_service.confirm_pending_action(False)
                if res:
                    return format_tool_result_context("action.cancel", res, self.tool_service.caller, reply_language), True
            else:
                return format_confirmation_required_context(tool_name, "your request", reply_language), True

        # 2. Identity Verification
        if intent == SupportIntent.VERIFY_IDENTITY:
            ids = extract_identifiers(text)
            ident = ids.get("account_id") or ids.get("phone") or ids.get("student_id") or ids.get("coach_id") or text.strip()
            verified = await self.tool_service.verify_caller(ident)
            if verified:
                return (
                    f"ACCOUNT_VERIFIED:\n"
                    f"The caller is verified as {self.tool_service.caller.role.value} ({self.tool_service.caller.name}). "
                    f"Account ID: {self.tool_service.caller.account_id}.\n"
                    "INSTRUCTION:\n"
                    "Greet the caller warmly, confirm that their account has been verified, "
                    "and ask how you can help them with their account today.",
                    True,
                )
            else:
                return (
                    "ACCOUNT_VERIFICATION_FAILED:\n"
                    "No account record matched the provided verification details.\n"
                    "INSTRUCTION:\n"
                    "Tell the caller politely that the account could not be found with those details. "
                    "Ask them to confirm their account ID or registered phone number.",
                    True,
                )

        # 3. Read Lookups
        if intent in (SupportIntent.SESSION_LOOKUP, SupportIntent.LESSON_LOOKUP):
            if not self.tool_service.caller.is_verified:
                return format_verification_required_context("to check session status", reply_language), True
            ids = extract_identifiers(text)
            res = await self.tool_service.execute_tool("session.lookup", ids)
            return format_tool_result_context("session.lookup", res, self.tool_service.caller, reply_language), True

        if intent == SupportIntent.SUBSCRIPTION_LOOKUP:
            if not self.tool_service.caller.is_verified:
                return format_verification_required_context("to check subscription details", reply_language), True
            ids = extract_identifiers(text)
            res = await self.tool_service.execute_tool("subscription.lookup", ids)
            return format_tool_result_context("subscription.lookup", res, self.tool_service.caller, reply_language), True

        if intent == SupportIntent.STUDENT_LOOKUP:
            if not self.tool_service.caller.is_verified:
                return format_verification_required_context("to access student details", reply_language), True
            ids = extract_identifiers(text)
            res = await self.tool_service.execute_tool("student.lookup", ids)
            return format_tool_result_context("student.lookup", res, self.tool_service.caller, reply_language), True

        if intent == SupportIntent.ACCOUNT_LOOKUP:
            if not self.tool_service.caller.is_verified:
                return format_verification_required_context("to view account details", reply_language), True
            ids = extract_identifiers(text)
            res = await self.tool_service.execute_tool("account.lookup", ids)
            return format_tool_result_context("account.lookup", res, self.tool_service.caller, reply_language), True

        # 4. Write Action Triggers (Confirmation Gates)
        if intent == SupportIntent.CREATE_TICKET:
            self.tool_service.stage_action("ticket.create", {"category": "support", "summary": text, "language": reply_language})
            return format_confirmation_required_context("create a support ticket", "for this issue", reply_language), True

        if intent == SupportIntent.CALLBACK_REQUEST:
            self.tool_service.stage_action("callback.create", {"reason": text, "language": reply_language})
            return format_confirmation_required_context("schedule a phone callback", "with our team", reply_language), True

        if intent == SupportIntent.FEEDBACK:
            res = await self.tool_service.execute_tool("feedback.create", {"text": text, "language": reply_language})
            return format_tool_result_context("feedback.create", res, self.tool_service.caller, reply_language), True

        if intent in (SupportIntent.ACADEMY_LEAD, SupportIntent.CUSTOM_PLAN_LEAD):
            lead_type = "custom_plan" if intent == SupportIntent.CUSTOM_PLAN_LEAD else "academy"
            res = await self.tool_service.execute_tool("lead.create", {"lead_type": lead_type, "summary": text, "language": reply_language})
            return format_tool_result_context("lead.create", res, self.tool_service.caller, reply_language), True

        if intent == SupportIntent.HUMAN_ESCALATION:
            res = await self.tool_service.execute_tool("escalation.prepare", {"issue": text, "language": reply_language})
            return (
                "HUMAN_ESCALATION_PREPARED:\n"
                "An escalation summary has been created for human representative follow-up.\n"
                "INSTRUCTION:\n"
                "Acknowledge the caller's request for a human representative warmly. "
                "Inform them that their request has been noted and a representative will follow up.",
                True,
            )

        return "", False

    # -- knowledge (Phase 5) ---------------------------------------------

    def _knowledge_context(self, text: str, reply_language: str) -> str:
        """Grounded context for this turn, or "" when retrieval is not
        needed / not available. Synchronous and in-memory (ms range), so
        a barge-in cancelling the turn discards it with the turn."""
        if self.knowledge is None:
            return ""
        if detect_language_switch(text) or self.is_ending(text):
            return ""
        if not self.knowledge.needs_knowledge(text):
            return ""
        return self.knowledge.answer_with_knowledge(
            text, context_turns=self.conversation.turns,
            language=reply_language).context

    # -- speaking ---------------------------------------------------------

    async def speak(self, text: str, language_code: str,
                    on_first_audio=None) -> None:
        """Stream ``text`` to the speaker; cancellable via player.cancel()."""
        if self.player is None:
            raise StreamingTTSError("No speaker player configured.")
        self.player.reset_for_next()
        if not self.tts.is_open:
            await self.tts.open(language_code)

        first_audio_marked = False

        async def on_chunk(mp3_bytes: bytes) -> None:
            nonlocal first_audio_marked
            if not first_audio_marked:
                first_audio_marked = True
                self.timings.first_audio = time.monotonic()
                if on_first_audio:
                    on_first_audio()
            # Decode in a worker thread to keep the event loop responsive.
            await asyncio.get_event_loop().run_in_executor(
                None, self.player.feed_mp3_chunk, mp3_bytes
            )

        await self.tts.synthesize(text, language_code, on_chunk)
        await asyncio.get_event_loop().run_in_executor(None, self.player.finish)

    # -- full turn -----------------------------------------------------

    def is_echo(self, transcript: str) -> bool:
        """True if the transcript matches the reply we're speaking."""
        return matches_spoken_echo(transcript, self.current_reply)

    def normalize_transcript(self, text: str) -> str:
        return correct_brand_terms(text)

    @staticmethod
    def is_ending(text: str) -> bool:
        lowered = text.strip().lower().rstrip(".!")
        return any(phrase in lowered for phrase in END_PHRASES)

    async def handle_final_transcript(
        self, text: str, language: str, on_first_audio=None
    ) -> str:
        """Full turn: brand-correct → LLM → streaming TTS. Returns reply."""
        corrected = self.normalize_transcript(text)
        tts_language = select_tts_language(language)
        reply = await self.generate_reply(corrected, language)
        await self.speak(reply, tts_language, on_first_audio=on_first_audio)
        return reply


def _safe_llm_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "Chat model authentication failure (check API key)."
    if status == 400:
        return "Chat model rejected the request (invalid parameters)."
    if status == 429:
        return "Chat model rate limit reached — try again shortly."
    if status is not None and 500 <= status < 600:
        return f"Chat model service error (HTTP {status})."
    name = type(exc).__name__.lower()
    if any(w in name for w in ("connect", "timeout")):
        return "Chat model network/connectivity failure."
    return f"Chat model request failed ({type(exc).__name__})."
