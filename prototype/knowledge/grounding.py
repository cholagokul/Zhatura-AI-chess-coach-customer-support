"""Zhatura AI Customer Care — grounding & honesty guards (Phase 5).

Turns retrieval hits into either:
  - a grounded LLM context (HIGH/MEDIUM confidence), or
  - a deterministic honesty context (LOW confidence, pricing guard,
    account-specific guard) that instructs the model to SAY there is no
    verified data instead of inventing one.

The LLM still phrases the fallback in the caller's language (the context
is an instruction, not spoken text), which keeps the multilingual voice
pipeline intact without ever letting general model knowledge fill gaps.
"""

from __future__ import annotations

from .models import AnswerMode, Confidence, RetrievalHit

HIGH_MIN_SCORE = 2.0
MEDIUM_MIN_SCORE = 1.0
MIN_HITS_FOR_HIGH = 1

# Hard pricing guard (§23): when no verified plan chunk with real
# content exists, a pricing question must produce this, never a price.
PRICING_UNAVAILABLE_STATEMENT = (
    "There is no verified Zhatura plan, package, subscription, price, "
    "discount, refund, renewal or free-trial information in the current "
    "knowledge base. Zhatura documentation does describe free access "
    "with limited coaching reviews and paid subscriptions with expanded "
    "access, but you must never invent exact prices, plan names or "
    "limits. Tell the caller clearly that current pricing and detailed "
    "subscription information should be confirmed through Zhatura "
    "Customer Support, and that you will not guess. Offer to help with "
    "other Zhatura questions or to note the question for the support "
    "team."
)

UNKNOWN_STATEMENT = (
    "The verified Zhatura knowledge base has no information answering "
    "this question. Tell the caller honestly that you don't have "
    "verified information about that yet — do NOT guess or fill the gap "
    "from general knowledge — and offer to help with Zhatura features, "
    "dashboards, the AI Chess Coach or general support instead."
)

ACCOUNT_LIMIT_STATEMENT = (
    "The caller is asking about their OWN account, child profile, "
    "subscription, payment or today's lesson/session. You can explain "
    "how the product works GENERALLY from verified knowledge, but you "
    "have NO access to any customer's account data in this phase. Say "
    "clearly that you cannot see their account or session status yet, "
    "and offer a support next step. Never say or imply that you "
    "checked, opened or inspected any account."
)


def classify_confidence(hits: "list[RetrievalHit]",
                        topic: "str | None") -> str:
    if not hits:
        return Confidence.LOW
    top = hits[0].score
    if top >= HIGH_MIN_SCORE or (top >= 1.5 and topic and
                                 hits[0].chunk.topic == topic):
        return Confidence.HIGH
    if top >= MEDIUM_MIN_SCORE:
        return Confidence.MEDIUM
    return Confidence.LOW


def has_verified_pricing_content(hits: "list[RetrievalHit]") -> bool:
    """True only if a retrieved chunk actually carries plan/pricing
    facts — an 'unavailable' plans chunk does NOT count."""
    for h in hits:
        if h.chunk.topic == "plans" and h.chunk.status == "available":
            return True
    return False
