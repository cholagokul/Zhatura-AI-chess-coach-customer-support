"""Phase 5 tests — Zhatura knowledge base + grounded answers.

Covers: loading (md/json/txt), chunking, metadata, validation,
duplicate detection, topic/audience detection, retrieval ranking,
follow-up context, brand-correction → retrieval, unknown fallback,
pricing + account hallucination guards, golden set, VoiceAgent
integration (grounded context injection, language suffix stays last,
trivial/end-call/switch bypass), per-turn latency, and production-vs-
fixture isolation. All mock-only: no Sarvam credits, no telephony.

Synthetic fixture data uses a fictional product ("Chessly") and lives
only under tests/fixtures/knowledge/ — it must never leak into the
production corpus.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from agent.brand_correction import correct_brand_terms  # noqa: E402
from agent.voice_agent import VoiceAgent  # noqa: E402
from knowledge import intents  # noqa: E402
from knowledge.grounding import (  # noqa: E402
    ACCOUNT_LIMIT_STATEMENT,
    PRICING_UNAVAILABLE_STATEMENT,
    classify_confidence,
)
from knowledge.loader import load_markdown, load_sources  # noqa: E402
from knowledge.models import (  # noqa: E402
    AnswerMode,
    Confidence,
    KnowledgeChunk,
)
from knowledge.retriever import Retriever  # noqa: E402
from knowledge.service import (  # noqa: E402
    DEFAULT_SOURCES_DIR,
    KnowledgeService,
)
from knowledge.store import KnowledgeStore  # noqa: E402
from knowledge.validate import validate_chunks  # noqa: E402

from tests.test_phase4_exotel import _cfg  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "knowledge"
GOLDEN = Path(__file__).resolve().parent / "golden" / "knowledge_golden.json"


@pytest.fixture(scope="module")
def service():
    return KnowledgeService()          # real production sources


# ---------------------------------------------------------------------
# loading / parsing / metadata
# ---------------------------------------------------------------------

class TestLoading:
    def test_production_sources_load(self, service):
        assert len(service.store) >= 20
        assert all(c.verified for c in service.store.all())

    def test_all_spec_documents_present(self):
        chunks = load_sources(DEFAULT_SOURCES_DIR)
        names = {c.source.rsplit("/", 1)[-1] for c in chunks}
        for expected in (
                "01_zhatura_overview.md", "02_ai_chess_coach.md",
                "03_student_features.md", "04_parent_features.md",
                "05_coach_features.md", "06_academy_features.md",
                "07_lessons_sessions.md", "08_game_analysis.md",
                "09_progress_tracking.md", "10_puzzles_training.md",
                "11_plans_pricing.md", "12_account_login_help.md",
                "13_technical_support.md", "14_multilingual_support.md",
                "15_faq.md", "16_escalation_support.md",
                "17_organization_custom_plans.md", "18_privacy_security.md",
                "19_supported_platforms.md",
                "20_common_customer_issues.md",
                "21_online_chess.md", "22_game_history.md",
                "23_future_roadmap.md"):
            assert expected in names

    def test_markdown_sections_become_chunks_with_metadata(self):
        chunks = load_markdown(
            DEFAULT_SOURCES_DIR / "04_parent_features.md")
        assert chunks
        c = chunks[0]
        assert c.source.endswith("04_parent_features.md")
        assert c.topic == "features"
        assert "parent" in c.audience
        assert c.section and c.title
        assert c.id.startswith("parent_features#")
        assert c.source_type == "approved_internal"

    def test_meta_block_parsed(self):
        chunks = load_markdown(DEFAULT_SOURCES_DIR / "11_plans_pricing.md")
        assert all(c.status == "unavailable" for c in chunks)
        assert all(c.source_type == "approved_internal" for c in chunks)
        assert all("provenance:" in t for c in chunks for t in c.tags)

    def test_doc_title_without_body_is_not_a_chunk(self):
        chunks = load_markdown(FIXTURES / "chessly_overview.md")
        assert all(c.content.strip() for c in chunks)
        assert all("Chessly Overview" not in c.id for c in chunks)

    def test_json_and_txt_loading(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps([{
            "id": "x#1", "title": "T", "topic": "faq",
            "audience": "general", "content": "hello world content here",
            "verified": True, "source_type": "json_fixture"}]))
        (tmp_path / "b.txt").write_text("plain text knowledge body " * 4)
        chunks = load_sources(tmp_path)
        assert {c.source_type for c in chunks} == {"json_fixture",
                                                   "approved_internal"}

    def test_production_corpus_has_no_fixture_facts(self, service):
        blob = " ".join(c.content for c in service.store.all()).lower()
        assert "chessly" not in blob
        assert "testcoins" not in blob


# ---------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------

class TestValidation:
    def test_production_corpus_validates_clean(self):
        issues = validate_chunks(load_sources(DEFAULT_SOURCES_DIR))
        assert issues == []

    def test_fixture_corpus_flagged(self):
        issues = validate_chunks(load_sources(FIXTURES))
        joined = "\n".join(issues)
        assert "duplicate content" in joined
        assert "NOT verified" in joined

    def test_duplicate_ids_detected(self):
        c = KnowledgeChunk(id="a#1", title="t", topic="faq",
                           audience="general", content="same body here",
                           source="x.md")
        issues = validate_chunks([c, c])
        assert any("duplicate chunk id" in i for i in issues)

    def test_missing_metadata_detected(self):
        c = KnowledgeChunk(id="b#1", title="t", topic="",
                           audience="general", content="body",
                           source="")
        issues = validate_chunks([c])
        assert any("missing source" in i for i in issues)
        assert any("missing topic" in i for i in issues)

    def test_suspicious_pricing_claim_flagged(self):
        c = KnowledgeChunk(id="p#1", title="t", topic="plans",
                           audience="general", source="plans.md",
                           status="available",
                           content="The family plan costs ₹499 per month.")
        issues = validate_chunks([c])
        assert any("suspicious plan/pricing claim" in i for i in issues)

    def test_production_pricing_corpus_has_no_numbers(self):
        chunks = load_sources(DEFAULT_SOURCES_DIR)
        plans = [c for c in chunks if c.topic == "plans"]
        assert plans and all(c.status == "unavailable" for c in plans)


# ---------------------------------------------------------------------
# topic / audience / guards
# ---------------------------------------------------------------------

class TestIntents:
    @pytest.mark.parametrize("text,expected", [
        ("What plans do you offer?", "plans"),
        ("How much does it cost?", "plans"),
        ("What does the parent dashboard show?", "dashboard"),
        ("How do lessons work?", "lessons"),
        ("Tell me about the AI Chess Coach", "ai_coach"),
        ("I cannot log in to my account", "account_help"),
        ("thank you so much", None),
    ])
    def test_topic_detection(self, text, expected):
        assert intents.detect_topic(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("I am a parent, what can I see?", "parent"),
        ("I run a chess academy with multiple students", "academy"),
        ("I am a coach", "coach"),
        ("What can my kid do?", "parent"),
        ("What is Zhatura?", None),
    ])
    def test_audience_detection(self, text, expected):
        assert intents.detect_audience(text) == expected

    def test_account_specific_requires_owner_and_problem(self):
        assert intents.is_account_specific(
            "My child cannot see today's lesson.")
        assert intents.is_account_specific("My login is not working.")
        assert not intents.is_account_specific(
            "What can I see about my child's progress?")

    def test_pricing_terms(self):
        assert intents.is_pricing_query("How much does Zhatura cost?")
        assert intents.is_pricing_query("कीमत क्या है?")
        assert intents.is_pricing_query("subscription renewal refund")
        assert not intents.is_pricing_query("What is Zhatura?")

    def test_needs_knowledge_skips_trivial(self):
        assert not intents.needs_knowledge("hello")
        assert not intents.needs_knowledge("thank you")
        assert not intents.needs_knowledge("okay")
        assert intents.needs_knowledge("what is Zhatura?")


# ---------------------------------------------------------------------
# retrieval + confidence + grounding
# ---------------------------------------------------------------------

class TestRetrieval:
    def test_relevant_question_ranks_correct_source(self, service):
        hits = service.retriever.retrieve("What can parents track?",
                                          audience="parent")
        assert hits
        assert hits[0].chunk.source.endswith(
            ("04_parent_features.md", "09_progress_tracking.md"))

    def test_coach_question_ranks_coach_source(self, service):
        # production flow passes the detected audience, exactly like the
        # service does — "coach" alone collides with the AI Chess Coach
        hits = service.retriever.retrieve("What can a coach monitor?",
                                          audience="coach")
        assert hits[0].chunk.source.endswith("coach_features.md")

    def test_brand_mishearing_corrected_before_retrieval(self, service):
        # STT mishearing "Jathura" must normalize to Zhatura first (§11)
        corrected = correct_brand_terms("What is Jathura?")
        assert "Zhatura" in corrected
        hits = service.retriever.retrieve(corrected)
        # overview AND faq carry the identical verified sentence — either
        # is a correct top source
        assert hits and hits[0].chunk.source.endswith(
            ("zhatura_overview.md", "faq.md"))

    def test_native_script_transcripts_still_retrieve(self, service):
        # saaras returns native-script transcripts even for code-mixed
        # speech (zero latin tokens) — native hints must supply the
        # retrieval tokens or grounding wrongly reports UNKNOWN.
        hits = service.retriever.retrieve(
            "பேரண்ட் டேஷ்போர்டில் என்ன விவரங்கள் இருக்கும்?",
            audience="parent")
        assert hits
        assert hits[0].chunk.source.endswith("parent_features.md")

        hits = service.retriever.retrieve("ఝతురా AI చెస్ కోచ్ ఏమిటి?")
        assert hits
        assert hits[0].chunk.source.endswith(
            ("ai_chess_coach.md", "faq.md"))

    def test_unverified_chunks_never_retrieved(self):
        store = KnowledgeStore()
        store.extend(load_sources(FIXTURES))
        retriever = Retriever(store)
        hits = retriever.retrieve("What is Chessly pricing checkers?")
        assert all(h.chunk.verified for h in hits)
        assert not any("broken" in h.chunk.id for h in hits)

    def test_confidence_buckets(self, service):
        assert classify_confidence(
            service.retriever.retrieve("parent dashboard progress"),
            "dashboard") == Confidence.HIGH
        assert classify_confidence([], None) == Confidence.LOW

    def test_retrieval_is_fast(self, service):
        a = service.answer_with_knowledge("What is Zhatura?")
        assert a.latency_ms < 100          # target: << 200–300 ms


class TestServiceModes:
    def test_grounded_for_known_product_question(self, service):
        a = service.answer_with_knowledge("What is Zhatura?")
        assert a.mode == AnswerMode.GROUNDED
        assert "VERIFIED ZHATURA KNOWLEDGE" in a.context
        assert "AI-powered chess learning platform" in a.context
        assert a.sources

    def test_unknown_for_unanswerable(self, service):
        # no verified corpus content matches at all
        store = KnowledgeStore()
        store.add(KnowledgeChunk(id="z#1", title="z", topic="overview",
                                 audience="general", source="z.md",
                                 content="completely unrelated body"))
        svc = KnowledgeService(store=store)
        a = svc.answer_with_knowledge("quantum entanglement pizza ovens")
        assert a.mode == AnswerMode.UNKNOWN
        assert "don't have verified information" in a.context.lower()

    def test_pricing_guard(self, service):
        a = service.answer_with_knowledge("How much does Zhatura cost?")
        assert a.mode == AnswerMode.PRICING_UNAVAILABLE
        assert PRICING_UNAVAILABLE_STATEMENT.split(".")[0] in a.context
        # the context must carry no price figures whatsoever
        assert "₹" not in a.context and "$" not in a.context

    def test_account_guard(self, service):
        a = service.answer_with_knowledge(
            "My child cannot see today's lesson.")
        assert a.mode == AnswerMode.ACCOUNT_LIMITED
        assert ACCOUNT_LIMIT_STATEMENT.split(".")[0] in a.context

    def test_parent_progress_question_stays_grounded(self, service):
        a = service.answer_with_knowledge(
            "What can I see about my child's progress?")
        assert a.mode == AnswerMode.GROUNDED
        assert "Parent Dashboard" in a.context

    def test_followup_inherits_topic(self, service):
        ctx = [{"role": "user",
                "content": "What does the parent dashboard show?"},
               {"role": "assistant",
                "content": "Parents can view progress."}]
        a = service.answer_with_knowledge("And coaches?",
                                          context_turns=ctx)
        assert a.mode == AnswerMode.GROUNDED
        assert any("coach_features.md" in s for s in a.sources)

    def test_source_refs_are_log_shaped(self, service):
        a = service.answer_with_knowledge("What can a coach do?")
        assert all("#" in s for s in a.sources)
        assert not any("callers" in s for s in a.sources)


# ---------------------------------------------------------------------
# golden answer set (§38)
# ---------------------------------------------------------------------

class TestGolden:
    CASES = json.loads(GOLDEN.read_text())["cases"]

    @pytest.mark.parametrize("case", CASES,
                             ids=[c["question"] for c in CASES])
    def test_golden_case(self, service, case):
        q = case["question"]
        if case.get("expect_mode") == "skipped":
            assert not service.needs_knowledge(q)
            return
        a = service.answer_with_knowledge(q)
        expected = case.get("expect_mode") or "|".join(
            case["expect_mode_any"])
        modes = case.get("expect_mode_any") or [case["expect_mode"]]
        assert a.mode in modes, f"{q!r}: got {a.mode}, want {expected}"
        ctx = a.context.lower()
        for needle in case["required_in_context"]:
            assert needle.lower() in ctx, f"{q!r}: missing {needle!r}"
        for needle in case["forbidden_in_context"]:
            assert needle.lower() not in ctx, \
                f"{q!r}: forbidden claim {needle!r} present"


# ---------------------------------------------------------------------
# VoiceAgent integration (mock chat client — no API)
# ---------------------------------------------------------------------

class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class FakeChatClient:
    """Captures messages; returns a canned reply."""

    def __init__(self, reply="Grounded test reply."):
        self.reply = reply
        self.calls = []

    class _Chat:
        pass

    @property
    def chat(self):
        return self

    async def completions(self, model=None, messages=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return _FakeResponse(self.reply)


def _agent(knowledge, reply="ok"):
    cfg = _cfg(knowledge_enabled=False)
    return VoiceAgent(cfg=cfg, chat_client=FakeChatClient(reply),
                      knowledge=knowledge)


class TestVoiceAgentKnowledge:
    def test_grounded_context_injected(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply("What is Zhatura?"))
        msgs = agent._client.calls[0]["messages"]
        ctx_msgs = [m for m in msgs if m["role"] == "system"
                    and "VERIFIED ZHATURA KNOWLEDGE" in m["content"]]
        assert ctx_msgs, "grounded context missing"
        assert "chess learning platform" in ctx_msgs[0]["content"]

    def test_language_suffix_stays_last_message(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply("Zhatura என்ன?", "ta-IN"))
        last = agent._client.calls[0]["messages"][-1]
        assert "Reply in Tamil (ta-IN)" in last["content"]
        # context sits BEFORE the language suffix
        msgs = agent._client.calls[0]["messages"]
        assert "VERIFIED" in msgs[-2]["content"] or \
            "MANDATORY" in msgs[-2]["content"]

    def test_trivial_turn_skips_retrieval(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply("thank you"))
        msgs = agent._client.calls[0]["messages"]
        assert not any("VERIFIED ZHATURA KNOWLEDGE" in m["content"]
                       or "MANDATORY" in m["content"] for m in msgs)

    def test_end_call_and_switch_bypass(self):
        service = KnowledgeService()
        agent = _agent(service)
        assert agent._knowledge_context("cut the call", "en-IN") == ""
        assert agent._knowledge_context("please speak Tamil",
                                        "ta-IN") == ""
        assert agent._knowledge_context("bye bye", "en-IN") == ""

    def test_knowledge_disabled_by_config(self):
        cfg = _cfg(knowledge_enabled=False)
        agent = VoiceAgent(cfg=cfg, chat_client=FakeChatClient())
        assert agent.knowledge is None

    def test_knowledge_default_enabled_and_loads(self):
        cfg = _cfg(knowledge_enabled=True)
        agent = VoiceAgent(cfg=cfg, chat_client=FakeChatClient())
        assert agent.knowledge is not None
        assert len(agent.knowledge.store) >= 20

    def test_pricing_turn_gets_guard_context(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply("What plans do you offer?"))
        msgs = agent._client.calls[0]["messages"]
        assert any("MANDATORY HONESTY RULE" in m["content"] and
                   "no verified" in m["content"] for m in msgs)

    def test_account_turn_gets_limit_context(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply(
            "My child cannot see today's session."))
        msgs = agent._client.calls[0]["messages"]
        assert any("NO access to any customer's account" in m["content"]
                   for m in msgs)

    def test_tanglish_query_grounded_in_caller_language_context(self):
        agent = _agent(KnowledgeService())
        asyncio.run(agent.generate_reply(
            "Parent dashboard la enna details irukum?",
            "ta-IN", reply_language="ta-IN"))
        msgs = agent._client.calls[0]["messages"]
        assert any("Parent Dashboard" in m["content"] for m in msgs)
        assert "Reply in Tamil" in msgs[-1]["content"]

    def test_conversation_records_normal_turns(self):
        agent = _agent(KnowledgeService(), reply="Answer here.")
        reply = asyncio.run(agent.generate_reply("What is Zhatura?"))
        assert reply == "Answer here."
        turns = agent.conversation.turns
        assert turns[-2]["role"] == "user"
        assert turns[-1]["content"] == "Answer here."
