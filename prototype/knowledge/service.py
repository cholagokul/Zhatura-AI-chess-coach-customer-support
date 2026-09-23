"""Zhatura AI Customer Care — KnowledgeService facade (Phase 5).

VoiceAgent calls ONLY this facade:

    service.answer_with_knowledge(query, context_turns, language,
                                  audience=None) -> KnowledgeAnswer

Pipeline: brand-corrected query → topic/audience detect → follow-up
context merge → hybrid retrieve → confidence → honesty guards →
grounded LLM context. Retrieval is synchronous and in-memory
(milliseconds), so it never blocks the turn loop and is trivially
cancellable with the turn (barge-in discards the whole turn).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import formatter, grounding, intents
from .loader import load_sources
from .models import AnswerMode, Confidence, KnowledgeAnswer
from .retriever import Retriever
from .store import KnowledgeStore

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_DIR = Path(__file__).resolve().parent / "sources"


class KnowledgeService:
    def __init__(self, sources_dir: "str | Path | None" = None,
                 store: "KnowledgeStore | None" = None):
        if store is None:
            store = KnowledgeStore()
            store.extend(load_sources(sources_dir or DEFAULT_SOURCES_DIR))
        self.store = store
        self.retriever = Retriever(store)
        self.last_latency_ms = 0

    # -- public -----------------------------------------------------------

    def needs_knowledge(self, text: str) -> bool:
        return intents.needs_knowledge(text)

    def answer_with_knowledge(self, query: str,
                              context_turns: "list[dict] | None" = None,
                              language: str = "en-IN",
                              audience: "str | None" = None
                              ) -> KnowledgeAnswer:
        t0 = time.monotonic()
        topic = intents.detect_topic(query)
        audience = audience or intents.detect_audience(query)
        # Follow-up support (§19): "And coaches?" carries no topic —
        # inherit the topic from the most recent user turn and enrich
        # the retrieval query with it, without changing the caller's
        # meaning.
        retrieval_query = query
        if topic is None and context_turns:
            for turn in reversed(context_turns[-4:]):
                if turn.get("role") != "user":
                    continue
                prev_text = turn.get("content", "")
                topic = intents.detect_topic(prev_text)
                if topic:
                    retrieval_query = f"{query} {topic}"
                    audience = audience or intents.detect_audience(prev_text)
                    break
        hits = self.retriever.retrieve(
            retrieval_query, topic=topic, audience=audience)
        confidence = grounding.classify_confidence(hits, topic)

        # Honesty guards (§22–§24). Account-specific guard wins over the
        # pricing guard ("my subscription not showing" is account
        # trouble, not a plan question); pure plan/price questions with
        # no verified plan data get the pricing guard.
        if intents.is_account_specific(query):
            mode = AnswerMode.ACCOUNT_LIMITED
            context = formatter.format_context(
                hits, mode, grounding.ACCOUNT_LIMIT_STATEMENT)
        elif intents.is_pricing_query(query) and (
                topic == "plans" or not grounding.
                has_verified_pricing_content(hits)):
            mode = AnswerMode.PRICING_UNAVAILABLE
            context = formatter.format_context(
                hits, mode, grounding.PRICING_UNAVAILABLE_STATEMENT)
        elif confidence == Confidence.LOW:
            mode = AnswerMode.UNKNOWN
            context = formatter.format_context(
                hits, mode, grounding.UNKNOWN_STATEMENT)
        else:
            mode = AnswerMode.GROUNDED
            context = formatter.format_context(hits, mode)

        latency_ms = round((time.monotonic() - t0) * 1000)
        self.last_latency_ms = latency_ms
        sources = formatter.source_refs(hits)
        # §21 debug logs — no caller numbers, no secrets.
        logger.info("KNOWLEDGE QUERY: topic=%s audience=%s", topic,
                    audience)
        logger.info("RETRIEVED: %s", ", ".join(
            f"{s} score={h.score:.2f}" for s, h in
            zip(sources, hits)) or "none")
        logger.info("GROUNDING: %s (mode=%s)", confidence, mode)
        logger.info("ANSWER SOURCE COUNT: %d. RETRIEVAL LATENCY: %d ms.",
                    len(sources), latency_ms)
        return KnowledgeAnswer(
            mode=mode, confidence=confidence, context=context,
            sources=sources, query=query, topic=topic,
            audience=audience, latency_ms=latency_ms,
            hits=tuple(hits))

    def reload(self) -> int:
        """Rebuild from disk (after knowledge files change)."""
        store = KnowledgeStore()
        store.extend(load_sources(DEFAULT_SOURCES_DIR))
        self.store = store
        self.retriever = Retriever(store)
        return len(store)
