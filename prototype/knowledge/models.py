"""Zhatura AI Customer Care — knowledge-layer data models (Phase 5).

A KnowledgeChunk is the atomic verified unit the retriever works with.
Every chunk carries its source metadata (which file, which section,
whether the content is verified) so answers are always traceable.
Never logs or stores caller data or secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Confidence:
    """Retrieval confidence buckets (never exposed to callers)."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AnswerMode:
    """How the answer should be produced.

    grounded           — verified chunks were retrieved; LLM answers
                         strictly from the supplied context.
    unknown            — nothing verified found; deterministic
                         "no verified information" context instead.
    pricing_unavailable— plan/price question with no verified plan data;
                         deterministic guard context (never invent).
    account_limited    — caller asked about their own account; grounded
                         general info plus an explicit "the assistant
                         cannot access accounts" statement.
    none               — trivial turn (greeting/thanks/switch/end-call);
                         no retrieval was needed.
    """
    GROUNDED = "grounded"
    UNKNOWN = "unknown"
    PRICING_UNAVAILABLE = "pricing_unavailable"
    ACCOUNT_LIMITED = "account_limited"
    NONE = "none"


@dataclass(frozen=True)
class KnowledgeChunk:
    """One verified, retrievable piece of Zhatura knowledge."""
    id: str
    title: str
    topic: str
    audience: str           # general | student | child | parent | coach |
                            # academy | organization (comma list allowed)
    content: str
    source: str             # e.g. "knowledge/sources/plans.md"
    section: str = ""       # heading within the source file
    source_type: str = "approved_internal"  # official_website |
                                             # approved_internal |
                                             # approved_pricing
    verified: bool = True
    tags: tuple = ()
    language: str = "en"
    last_updated: str = ""
    priority: int = 0       # higher wins ties
    status: str = "available"   # "available" | "unavailable":
                                # "unavailable" chunks exist ONLY to
                                # ground the honest "not documented yet"
                                # answer; they never carry invented facts.
    confidence: str = ""        # optional: curator confidence label
    approved_by: str = ""       # optional: who approved this fact
    source_url: str = ""        # optional: public/approved URL
    version: str = ""           # optional: document version



@dataclass
class RetrievalHit:
    chunk: KnowledgeChunk
    score: float


@dataclass
class KnowledgeAnswer:
    """Result of one knowledge lookup for one caller turn."""
    mode: str                       # AnswerMode.*
    confidence: str                 # Confidence.*
    context: str = ""               # grounded context for the LLM
    sources: tuple = ()             # ["plans.md#plans", ...] logs only
    query: str = ""
    topic: "str | None" = None
    audience: "str | None" = None
    latency_ms: int = 0
    hits: tuple = field(default_factory=tuple)
