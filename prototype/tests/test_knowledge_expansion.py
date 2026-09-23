"""Knowledge expansion tests (2026-09-23 upgrade).

Covers the verified product-information expansion:
- product overview, My Zhatura Coach, online chess, matchmaking,
  ratings, game analysis, guardian controls, safety, mobile,
  free/premium wording (no invented prices),
- FUTURE marking for tournaments, academy expansion, smart boards,
  video coaching classrooms,
- no active-game move-assistance claims,
- voice-grounded answers, hallucination guards, support search.

Mock-only: no Sarvam credits, no telephony.
"""

import json
import re
import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from knowledge.loader import load_sources  # noqa: E402
from knowledge.models import AnswerMode  # noqa: E402
from knowledge.service import DEFAULT_SOURCES_DIR, KnowledgeService  # noqa: E402
from knowledge.validate import validate_chunks  # noqa: E402
from support.knowledge_data import get_support_knowledge_payload  # noqa: E402


@pytest.fixture(scope="module")
def service():
    return KnowledgeService()


@pytest.fixture(scope="module")
def corpus_blob(service):
    return " ".join(c.content for c in service.store.all())


@pytest.fixture(scope="module")
def payload():
    return get_support_knowledge_payload()


# ---------------------------------------------------------------------
# documented product knowledge exists
# ---------------------------------------------------------------------

class TestDocumentedKnowledge:
    def test_product_overview_exists(self, service):
        a = service.answer_with_knowledge("What is Zhatura?")
        assert a.mode == AnswerMode.GROUNDED
        assert "ai-powered chess learning platform" in a.context.lower()

    def test_overview_covers_core_audiences(self, corpus_blob):
        low = corpus_blob.lower()
        for word in ("beginner", "young learner", "parent", "coach",
                     "academ"):
            assert word in low, f"overview missing audience: {word}"

    def test_my_zhatura_coach_knowledge_exists(self, service):
        a = service.answer_with_knowledge("What is My Zhatura Coach?")
        assert a.mode == AnswerMode.GROUNDED
        assert "my zhatura coach" in a.context.lower()
        assert any("ai_chess_coach.md" in s or "faq.md" in s
                   for s in a.sources)

    def test_online_chess_retrieval(self, service):
        a = service.answer_with_knowledge(
            "Can I play chess against other players?")
        assert a.mode == AnswerMode.GROUNDED
        assert any("online_chess.md" in s for s in a.sources), a.sources

    def test_matchmaking_retrieval(self, service):
        a = service.answer_with_knowledge("Does Zhatura have matchmaking?")
        assert a.mode == AnswerMode.GROUNDED
        low = a.context.lower()
        assert "matchmaking" in low
        assert "comparable" in low or "balanced" in low

    def test_ratings_retrieval(self, service):
        a = service.answer_with_knowledge("Does Zhatura use player ratings?")
        assert a.mode == AnswerMode.GROUNDED
        low = a.context.lower()
        assert "rating" in low
        assert "competitive progress" in low

    def test_game_analysis_retrieval(self, service):
        a = service.answer_with_knowledge("Can Zhatura analyze my games?")
        assert a.mode == AnswerMode.GROUNDED
        low = a.context.lower()
        assert "turning point" in low or "missed opportunit" in low

    def test_game_history_retrieval(self, service):
        a = service.answer_with_knowledge("Can I review old games?")
        assert a.mode == AnswerMode.GROUNDED
        assert any("game_history.md" in s for s in a.sources) or \
            "game history" in a.context.lower()

    def test_parent_guardian_knowledge(self, service):
        a = service.answer_with_knowledge(
            "Can parents review their child's activity?")
        assert a.mode == AnswerMode.GROUNDED
        low = a.context.lower()
        assert "consent" in low
        assert "reviewing activity" in low or "review activity" in low

    def test_safety_knowledge(self, corpus_blob, service):
        low = corpus_blob.lower()
        for term in ("private profiles", "restricted communication",
                     "reporting", "blocking"):
            assert term in low, f"safety feature missing: {term}"
        a = service.answer_with_knowledge(
            "Does Zhatura support safety controls for young players?")
        assert a.mode == AnswerMode.GROUNDED

    def test_mobile_knowledge(self, corpus_blob, service):
        low = corpus_blob.lower()
        assert "android" in low
        assert "ios" in low
        a = service.answer_with_knowledge("Can I use Zhatura on mobile?")
        assert a.mode == AnswerMode.GROUNDED
        assert "android" in a.context.lower()

    def test_training_and_puzzles_knowledge(self, corpus_blob):
        low = corpus_blob.lower()
        assert "tactical exercises" in low
        assert "mistakes from previous games" in low

    def test_corpus_validates_clean_after_expansion(self):
        issues = validate_chunks(load_sources(DEFAULT_SOURCES_DIR))
        assert issues == [], "\n".join(issues)


# ---------------------------------------------------------------------
# free / premium wording — never invents prices
# ---------------------------------------------------------------------

class TestFreePremiumSafety:
    def test_free_premium_documented(self, corpus_blob):
        low = corpus_blob.lower()
        assert "free accounts may receive limited coaching reviews" in low
        assert "paid subscriptions may provide expanded access" in low

    def test_free_premium_sections_have_no_price_figures(self, service):
        chunks = [c for c in service.store.all()
                  if "free" in c.content.lower()
                  and "premium" in (c.section or "").lower()
                  or "free and paid" in (c.section or "").lower()
                  or "free access" in (c.section or "").lower()]
        assert chunks, "expected free/premium sections"
        for c in chunks:
            assert "₹" not in c.content and "$" not in c.content
            assert not re.search(r"\d+\s?(?:inr|usd|rupees?)", c.content,
                                 re.IGNORECASE)
            assert "per month" not in c.content.lower()
            assert "per year" not in c.content.lower()

    def test_no_invented_prices_in_corpus(self, corpus_blob):
        assert "₹" not in corpus_blob
        assert "$" not in corpus_blob

    def test_monthly_price_question_never_invents_price(self, service):
        a = service.answer_with_knowledge(
            "What is the Zhatura monthly price?")
        assert a.mode == AnswerMode.PRICING_UNAVAILABLE
        assert "₹" not in a.context and "$" not in a.context
        assert "per month" not in a.context.lower()
        assert not re.search(r"\b\d{2,}\b", a.context), \
            "pricing context must not carry amount digits"

    def test_support_confirmation_wording_present(self, corpus_blob):
        low = corpus_blob.lower()
        assert "confirmed through zhatura customer support" in low or \
            "zhatura customer support" in low


# ---------------------------------------------------------------------
# FUTURE capabilities are never described as current
# ---------------------------------------------------------------------

FUTURE_ITEMS = {
    "tournaments": "tournament",
    "expanded academy management": "expanded academy management",
    "smart-board connections": "smart-board connections",
    "video coaching classrooms": "video coaching classrooms",
}


class TestFutureRoadmapMarked:
    @pytest.mark.parametrize("label,needle", list(FUTURE_ITEMS.items()))
    def test_future_item_documented_with_future_status(
            self, service, label, needle):
        a = service.answer_with_knowledge(label)
        low = a.context.lower()
        assert needle in low, f"{label}: missing from context"
        assert "future" in low, f"{label}: not marked FUTURE"

    def test_future_sections_carry_status_future(self):
        chunks = load_sources(DEFAULT_SOURCES_DIR)
        roadmap = [c for c in chunks
                   if c.source.endswith("23_future_roadmap.md")]
        assert roadmap
        for c in roadmap:
            if c.section == "Status of this document":
                continue
            assert "status: future" in (c.title + " " + c.content).lower() \
                or "future" in c.content.lower(), c.id

    def test_never_says_currently_provides_future_items(self, corpus_blob):
        low = corpus_blob.lower()
        for label in FUTURE_ITEMS:
            assert f"zhatura currently provides {label}" not in low
            assert f"zhatura currently offers {label}" not in low

    def test_tournament_question_explains_future_status(self, service):
        a = service.answer_with_knowledge(
            "When can I join a Zhatura tournament?")
        assert a.mode in (AnswerMode.GROUNDED, AnswerMode.UNKNOWN)
        low = a.context.lower()
        assert "future" in low
        assert "currently" not in low or "not a current" in low or \
            "not described as a current" in low

    def test_academy_scale_question_does_not_invent_limit(self, service):
        a = service.answer_with_knowledge(
            "How many students can my academy manage?")
        assert a.mode == AnswerMode.GROUNDED
        low = a.context.lower()
        assert "not yet documented" in low
        assert "10,000" not in low
        assert "unlimited" not in low
        assert not re.search(r"\b\d{3,}\b", low), \
            "academy limits must not carry invented numbers"


# ---------------------------------------------------------------------
# no active-game move assistance claims
# ---------------------------------------------------------------------

class TestNoLiveMoveAssistance:
    def test_active_game_disclaimer_documented(self, corpus_blob):
        low = corpus_blob.lower()
        assert "not for giving players moves during an active " \
            "competitive game" in low

    def test_best_move_question_answered_with_disclaimer(self, service):
        a = service.answer_with_knowledge(
            "Does Zhatura tell me the best move while I am playing?")
        assert a.mode in (AnswerMode.GROUNDED, AnswerMode.UNKNOWN)
        low = a.context.lower()
        assert "does not provide" in low or "not for giving players moves" \
            in low
        forbidden = (
            "provides the best move during",
            "gives you the best move while",
            "suggests moves during an active",
            "live move assistance is available",
        )
        for phrase in forbidden:
            assert phrase not in low

    def test_no_chunk_claims_live_move_help(self, corpus_blob):
        low = corpus_blob.lower()
        # the only mentions of giving moves must be NEGATED statements
        for match in re.finditer(r"provide[sd]? moves", low):
            window = low[max(0, match.start() - 80):match.start()]
            assert "not" in window or "does not" in window or \
                "never" in window, low[max(0, match.start() - 80):
                                        match.end()]


# ---------------------------------------------------------------------
# hallucination test prompts (§42)
# ---------------------------------------------------------------------

class TestHallucinationPrompts:
    def test_monthly_price_prompt(self, service):
        a = service.answer_with_knowledge(
            "What is the Zhatura monthly price?")
        assert a.mode == AnswerMode.PRICING_UNAVAILABLE
        assert "₹" not in a.context and "$" not in a.context
        assert "never" in a.context.lower()

    def test_tournament_timing_prompt(self, service):
        a = service.answer_with_knowledge(
            "When can I join a Zhatura tournament?")
        low = a.context.lower()
        assert "future" in low
        # no invented launch date
        assert not re.search(r"\b(?:launches|releasing|available now)\b",
                             low)

    def test_live_best_move_prompt(self, service):
        a = service.answer_with_knowledge(
            "Does Zhatura tell me the best move while I am playing?")
        low = a.context.lower()
        assert "does not provide" in low or "not for giving players moves" \
            in low

    def test_academy_student_limit_prompt(self, service):
        a = service.answer_with_knowledge(
            "How many students can my academy manage?")
        low = a.context.lower()
        assert "not yet documented" in low
        assert not re.search(r"\b\d{3,}\b", low)


# ---------------------------------------------------------------------
# voice grounding still works for new knowledge
# ---------------------------------------------------------------------

class TestVoiceGroundingExpanded:
    def _agent(self, knowledge):
        from agent.voice_agent import VoiceAgent

        class _Msg:
            def __init__(self, content):
                self.content = content

        class _Choice:
            def __init__(self, content):
                self.message = _Msg(content)

        class _Resp:
            def __init__(self, content):
                self.choices = [_Choice(content)]

        class _Client:
            def __init__(self):
                self.calls = []

            class chat:
                pass

            @property
            def chat(self):
                return self

            async def completions(self, model=None, messages=None, **kw):
                self.calls.append({"messages": messages})
                return _Resp("ok")

        from tests.test_phase4_exotel import _cfg
        cfg = _cfg(knowledge_enabled=False)
        return VoiceAgent(cfg=cfg, chat_client=_Client(),
                          knowledge=knowledge)

    @pytest.mark.parametrize("question,needle", [
        ("What is My Zhatura Coach?", "My Zhatura Coach"),
        ("Does Zhatura have matchmaking?", "matchmaking"),
        ("Can I use Zhatura on mobile?", "Android"),
    ])
    def test_voice_system_context_grounded(self, question, needle):
        import asyncio
        agent = self._agent(KnowledgeService())
        asyncio.run(agent.generate_reply(question))
        ctx = [m["content"] for m in agent._client.calls[0]["messages"]
               if m["role"] == "system"]
        joined = "\n".join(ctx)
        assert "VERIFIED ZHATURA KNOWLEDGE" in joined or \
            "MANDATORY HONESTY RULE" in joined
        assert needle.lower() in joined.lower()

    def test_pricing_voice_context_still_guarded(self):
        import asyncio
        agent = self._agent(KnowledgeService())
        asyncio.run(agent.generate_reply("What is the monthly price?"))
        joined = "\n".join(
            m["content"] for m in agent._client.calls[0]["messages"]
            if m["role"] == "system")
        assert "MANDATORY HONESTY RULE" in joined
        assert "₹" not in joined and "$" not in joined


# ---------------------------------------------------------------------
# support website search finds the new topics
# ---------------------------------------------------------------------

class TestSupportSearchTopics:
    @pytest.mark.parametrize("term", [
        "zhatura", "ai chess coach", "my zhatura coach", "online chess",
        "matchmaking", "ratings", "game analysis", "game review",
        "mistakes", "training", "puzzles", "game history", "parents",
        "guardian", "privacy", "safety", "free", "premium", "android",
        "ios", "coach", "academy", "tournament",
    ])
    def test_search_term_finds_results(self, payload, term):
        q = term.lower()
        hits = []
        for art in payload["articles"]:
            hay = " ".join(
                [art["title"], art.get("summary", ""),
                 art["category_title"]]
                + [s["title"] + " " + s["content"] for s in art["sections"]]
            ).lower()
            if q in hay:
                hits.append(art["id"])
        for faq in payload["faqs"]:
            hay = (faq["question"] + " " + faq["answer"]).lower()
            if q in hay:
                hits.append("faq")
        assert hits, f"no support-search results for {term!r}"

    def test_payload_has_future_category(self, payload):
        cat_ids = {c["id"] for c in payload["categories"]}
        assert "planned-features" in cat_ids
        assert "online-chess" in cat_ids

    def test_payload_faq_count_grew(self, payload):
        assert len(payload["faqs"]) >= 25

    def test_payload_free_premium_answers_have_no_prices(self, payload):
        blob = json.dumps(payload)
        assert "₹" not in blob
        # no dollar amounts either
        assert not re.search(r"\$\s?\d", blob)
