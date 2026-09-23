"""Zhatura AI Customer Care — grounded-context formatting (Phase 5).

Builds the system-message block handed to the LLM. Internal only:
filenames/ids go to logs (§20), the caller hears a natural answer.
The block always ends with the voice-first + honesty instruction.
"""

from __future__ import annotations

from .models import AnswerMode, RetrievalHit

_MAX_CHUNKS = 4
_MAX_CHUNK_CHARS = 900          # keep prompts voice-sized

_RULES = (
    "Rules: answer ONLY from the verified Zhatura knowledge above. "
    "If it does not answer the caller's question, say you don't have "
    "verified information about that yet — never invent features, "
    "prices, plans, policies, account or session status. Keep the "
    "answer short, natural and spoken-style (1–3 sentences); for big "
    "topics give a short summary and offer to go deeper. Answer in the "
    "caller's current language."
)


def _clip(text: str, limit: int = _MAX_CHUNK_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def format_context(hits: "list[RetrievalHit]", mode: str,
                   statement: str = "") -> str:
    """Return the system-message context for one turn."""
    lines = []
    if mode == AnswerMode.GROUNDED:
        lines.append("VERIFIED ZHATURA KNOWLEDGE (use only this for "
                     "Zhatura-specific facts):")
        for hit in hits[:_MAX_CHUNKS]:
            c = hit.chunk
            lines.append(f"— {c.title}: {_clip(c.content)}")
            if c.status == "unavailable":
                lines.append("  (This entry documents that the topic is "
                             "NOT yet covered by verified sources; say so "
                             "rather than guessing.)")
        lines.append(_RULES)
    else:
        # unknown / pricing_unavailable / account_limited: deterministic
        # honesty statement the model must voice in the caller's language.
        out = []
        if hits:
            out.append("VERIFIED ZHATURA KNOWLEDGE (partial — may support "
                       "only a general explanation):")
            for h in hits[:_MAX_CHUNKS]:
                out.append(f"— {h.chunk.title}: {_clip(h.chunk.content)}")
        out.append(f"MANDATORY HONESTY RULE: {statement}")
        out.append("Voice the rule's message naturally and briefly in the "
                   "caller's current language. Do not add facts beyond it "
                   "and the verified knowledge above.")
        return "\n".join(out)
    return "\n".join(lines)


def source_refs(hits: "list[RetrievalHit]") -> "tuple[str, ...]":
    """Log-only source references like 'parent_features.md#progress'."""
    refs = []
    for h in hits[:_MAX_CHUNKS]:
        c = h.chunk
        name = c.source.rsplit("/", 1)[-1]
        refs.append(f"{name}#{c.section}" if c.section else name)
    return tuple(refs)
