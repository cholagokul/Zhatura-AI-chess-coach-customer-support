"""Zhatura AI Customer Care — trusted knowledge layer (Phase 5).

Grounded customer-support answers from verified Zhatura sources only.
Public surface: KnowledgeService (service.py). Everything else is
internal plumbing: models, intents, loader, store, retriever,
grounding, formatter, validate.

    from knowledge.service import KnowledgeService
    svc = KnowledgeService()                      # loads sources/
    answer = svc.answer_with_knowledge(
        "What plans do you offer?",
        context_turns=conversation.turns,
        language="ta-IN")
    # answer.context → system-message block for the LLM
    # answer.sources → log-only provenance
"""

from .models import (  # noqa: F401
    AnswerMode,
    Confidence,
    KnowledgeAnswer,
    KnowledgeChunk,
)
from .service import KnowledgeService  # noqa: F401
