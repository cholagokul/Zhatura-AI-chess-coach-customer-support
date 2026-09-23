"""Phase 6 tests — knowledge expansion, source provenance, gaps and
retrieval quality across the expanded corpus.

Mock-only: no Sarvam credits used.
"""

import json
import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from knowledge import intents  # noqa: E402
from knowledge.loader import load_sources  # noqa: E402
from knowledge.models import AnswerMode, KnowledgeChunk  # noqa: E402
from knowledge.retriever import Retriever  # noqa: E402
from knowledge.service import DEFAULT_SOURCES_DIR, KnowledgeService  # noqa: E402
from knowledge.store import KnowledgeStore  # noqa: E402
from knowledge.validate import (  # noqa: E402
    _FIXTURE_LEAKS,
    _PLACEHOLDER_RE,
    _UNAPPROVED_PRICE_WORDS,
    knowledge_gaps,
    validate_chunks,
)


@pytest.fixture(scope="module")
def service():
    return KnowledgeService()


class TestKnowledgeExpansion:
    def test_twenty_sources_loaded(self, service):
        sources = {c.source.rsplit("/", 1)[-1] for c in service.store.all()}
        assert len(sources) == 20, sources

    def test_chunk_count_increased(self, service):
        # 20 documents produce many semantic chunks; must be well above
        # the Phase 5 count of 24.
        assert len(service.store) >= 70

    def test_all_chunks_verified(self, service):
        assert all(c.verified for c in service.store.all())

    def test_all_chunks_have_source_type(self, service):
        assert all(c.source_type for c in service.store.all())

    def test_source_type_values_are_reasonable(self, service):
        for c in service.store.all():
            assert c.source_type in (
                "official_website", "approved_internal", "approved_pricing")

    def test_production_corpus_has_no_fixture_leaks(self, service):
        blob = " ".join(c.content for c in service.store.all()).lower()
        for leak in _FIXTURE_LEAKS:
            assert leak not in blob, f"fixture leak: {leak}"

    def test_no_placeholder_text_in_production(self, service):
        for c in service.store.all():
            assert not _PLACEHOLDER_RE.search(c.content), \
                f"placeholder text in {c.id}"


class TestValidation:
    def test_corpus_validates_clean(self, service):
        issues = validate_chunks(service.store.all())
        assert issues == [], "\n".join(issues)

    def test_unapproved_pricing_claim_flagged(self):
        bad = KnowledgeChunk(
            id="p#1", title="t", topic="plans", audience="general",
            source="plans.md", source_type="approved_internal",
            status="available",
            content="The Pro plan is ₹999 per month.")
        issues = validate_chunks([bad])
        assert any("unapproved pricing claim" in i for i in issues)

    def test_fixture_content_leak_detected(self):
        bad = KnowledgeChunk(
            id="f#1", title="t", topic="faq", audience="general",
            source="x.md", source_type="approved_internal",
            content="Chessly gives 7000 testcoins.")
        issues = validate_chunks([bad])
        assert any("test-fixture content leak" in i for i in issues)


class TestRetrievalEvaluation:
    """§14 retrieval-quality checks."""

    def test_zhatura_overview_retrieval(self, service):
        topic = intents.detect_topic("What is Zhatura?")
        hits = service.retriever.retrieve("What is Zhatura?", topic=topic)
        assert hits[0].chunk.topic in ("overview", "faq")

    def test_ai_chess_coach_retrieval(self, service):
        topic = intents.detect_topic("What does the AI Chess Coach do?")
        hits = service.retriever.retrieve(
            "What does the AI Chess Coach do?", topic=topic)
        assert hits[0].chunk.topic == "ai_coach"

    def test_children_learning_chess_retrieval(self, service):
        topic = intents.detect_topic(
            "How does Zhatura help children learn chess?")
        hits = service.retriever.retrieve(
            "How does Zhatura help children learn chess?", topic=topic)
        assert hits[0].chunk.topic in ("overview", "ai_coach")

    def test_parent_features_retrieval(self, service):
        hits = service.retriever.retrieve(
            "What can parents see?", audience="parent")
        assert hits[0].chunk.source.endswith(
            ("04_parent_features.md", "09_progress_tracking.md"))

    def test_coach_features_retrieval(self, service):
        hits = service.retriever.retrieve(
            "What can coaches do?", audience="coach")
        assert hits[0].chunk.source.endswith("05_coach_features.md")

    def test_academy_retrieval(self, service):
        hits = service.retriever.retrieve(
            "Can academies use Zhatura?", audience="academy")
        assert hits[0].chunk.source.endswith("06_academy_features.md")

    def test_lessons_retrieval(self, service):
        topic = intents.detect_topic("How do lessons work?")
        hits = service.retriever.retrieve("How do lessons work?", topic=topic)
        assert hits[0].chunk.topic == "lessons"

    def test_session_retrieval(self, service):
        topic = intents.detect_topic("What is a session?")
        hits = service.retriever.retrieve("What is a session?", topic=topic)
        assert hits[0].chunk.topic == "lessons"

    def test_game_analysis_retrieval(self, service):
        topic = intents.detect_topic("Does Zhatura analyze games?")
        hits = service.retriever.retrieve(
            "Does Zhatura analyze games?", topic=topic)
        assert hits[0].chunk.topic == "game_analysis"

    def test_puzzles_retrieval(self, service):
        topic = intents.detect_topic("Does Zhatura give puzzles?")
        hits = service.retriever.retrieve(
            "Does Zhatura give puzzles?", topic=topic)
        assert hits[0].chunk.topic == "puzzles"

    def test_progress_tracking_retrieval(self, service):
        topic = intents.detect_topic("How does progress tracking work?")
        hits = service.retriever.retrieve(
            "How does progress tracking work?", topic=topic)
        assert hits[0].chunk.topic == "progress"

    def test_account_specific_detection(self):
        assert intents.is_account_specific(
            "My child cannot see today's lesson.")
        assert not intents.is_account_specific(
            "What can parents see?")


class TestGroundingModes:
    def test_pricing_question_gets_pricing_unavailable(self, service):
        a = service.answer_with_knowledge("What plans do you offer?")
        assert a.mode == AnswerMode.PRICING_UNAVAILABLE

    def test_price_question_no_numbers(self, service):
        a = service.answer_with_knowledge("How much does Zhatura cost?")
        assert a.mode == AnswerMode.PRICING_UNAVAILABLE
        assert "₹" not in a.context and "$" not in a.context

    def test_account_question_gets_account_limited(self, service):
        a = service.answer_with_knowledge(
            "My child cannot see today's session.")
        assert a.mode == AnswerMode.ACCOUNT_LIMITED

    def test_unknown_question_does_not_hallucinate(self, service):
        a = service.answer_with_knowledge("Can Zhatura book my flight?")
        assert a.mode in (AnswerMode.UNKNOWN, AnswerMode.GROUNDED)
        assert "flight" not in a.context.lower() or "don't have" in \
            a.context.lower()

    def test_followup_context_lesson_then_account(self, service):
        ctx = [{"role": "user", "content": "How do lessons work?"}]
        a = service.answer_with_knowledge(
            "What if my child cannot see one?", context_turns=ctx)
        # The account-specific guard must still fire despite lesson topic.
        assert a.mode == AnswerMode.ACCOUNT_LIMITED


class TestKnowledgeGaps:
    def test_gaps_list_generated(self, service):
        gaps = knowledge_gaps(service.store.all())
        assert gaps
        # pricing and lesson mechanics are known gaps
        topics = {g["topic"] for g in gaps}
        assert "plans" in topics

    def test_gaps_report_has_no_fixture_leaks(self, service):
        gaps = knowledge_gaps(service.store.all())
        text = json.dumps(gaps, ensure_ascii=False).lower()
        for leak in _FIXTURE_LEAKS:
            assert leak not in text


class TestLatency:
    def test_retrieval_latency_stays_low(self, service):
        import statistics
        lat = []
        for _ in range(50):
            a = service.answer_with_knowledge(
                "What can coaches do with batches?")
            lat.append(a.latency_ms)
        assert statistics.mean(lat) < 2  # ms; Phase 5 baseline was ~0.07 ms
