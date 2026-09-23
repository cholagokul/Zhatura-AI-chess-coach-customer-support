"""Zhatura AI Customer Care — knowledge validation (Phase 5).

`validate_chunks(chunks)` returns a list of human-readable issues; an
empty list means the corpus is clean. Used by build_index and tests.

Checks (§26): empty documents/chunks, duplicate ids, missing source
metadata, unverified chunks, duplicate content, and suspicious
plan/pricing claims (digits/₹/$/% near pricing words) flagged for
manual review — the honest corpus currently contains NO numbers.
"""

from __future__ import annotations

import re

from .models import KnowledgeChunk

_PRICE_CLAIM_RE = re.compile(
    r"(?:₹|\$|€|\b\d+\s?(?:inr|usd|rupees?|rs\.?)\b|"
    r"\b(?:price|cost|fee|plan|subscription|discount|refund|trial)s?\b"
    r"[^.\n]{0,40}\d|\d[^.\n]{0,40}\b(?:per month|monthly|yearly|"
    r"annually|per year|off|% off)\b)",
    re.IGNORECASE,
)

# Pricing-related keywords that are only allowed in source_type =
# approved_pricing when status = available.
_UNAPPROVED_PRICE_WORDS = re.compile(
    r"\b(price|pricing|cost|fee|subscription|discount|refund|renewal|"
    r"trial|monthly|yearly|per month|per year)\b",
    re.IGNORECASE,
)


_PLACEHOLDER_RE = re.compile(
    r"\b(lorem ipsum|xxxx|fixme|sample content|test fixture|"
    r"approved plan pending|copy the approved|replace this placeholder)\b",
    re.IGNORECASE,
)


# Common fixture/test product names that must never leak into production.
_FIXTURE_LEAKS = ("chessly", "testcoins", "samplecorp", "example product")


def validate_chunks(chunks: "list[KnowledgeChunk]") -> "list[str]":
    issues: "list[str]" = []
    seen_ids: "set[str]" = set()
    seen_content: "dict[str, str]" = {}
    if not chunks:
        issues.append("no knowledge chunks loaded at all")
        return issues
    for c in chunks:
        if not c.id:
            issues.append("chunk with missing id")
        elif c.id in seen_ids:
            issues.append(f"duplicate chunk id: {c.id}")
        seen_ids.add(c.id)
        if not c.content.strip():
            issues.append(f"{c.id}: empty content")
        if not c.source:
            issues.append(f"{c.id}: missing source metadata")
        if not c.topic:
            issues.append(f"{c.id}: missing topic")
        if not c.source_type:
            issues.append(f"{c.id}: missing source_type")
        if not c.verified:
            issues.append(f"{c.id}: NOT verified — excluded from "
                          "grounding until verified=true")
        key = " ".join(c.content.lower().split())
        if key and key in seen_content:
            issues.append(f"{c.id}: duplicate content of "
                          f"{seen_content[key]}")
        elif key:
            seen_content[key] = c.id
        if _PLACEHOLDER_RE.search(c.content):
            issues.append(f"{c.id}: placeholder or unverified text detected")
        lower = c.content.lower()
        if any(leak in lower for leak in _FIXTURE_LEAKS):
            issues.append(f"{c.id}: test-fixture content leak detected")
        if c.status == "available" and (
                c.topic == "plans" or c.source_type != "approved_pricing"):
            if _UNAPPROVED_PRICE_WORDS.search(c.content):
                # If this is an explicit "unavailable" explanation, it is
                # allowed as long as it does not invent numbers.
                if c.status == "available" and _PRICE_CLAIM_RE.search(c.content):
                    issues.append(f"{c.id}: unapproved pricing claim — "
                                  "status=available but no "
                                  "source_type=approved_pricing")
        if c.topic == "plans" and c.status == "available" and (
                _PRICE_CLAIM_RE.search(c.content)):
            issues.append(f"{c.id}: suspicious plan/pricing claim — "
                          "manual review required before shipping")
    return issues


def knowledge_gaps(chunks: "list[KnowledgeChunk]") -> "list[dict]":
    """Return a list of unavailable sections with their source."""
    gaps = []
    for c in chunks:
        if c.status == "unavailable":
            gaps.append({
                "id": c.id,
                "topic": c.topic,
                "audience": c.audience,
                "source": c.source.rsplit("/", 1)[-1],
                "section": c.section,
                "summary": " ".join(c.content.split())[:200],
            })
    return gaps
