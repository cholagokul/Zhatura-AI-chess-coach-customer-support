"""Zhatura AI Customer Care — hybrid retrieval (Phase 5).

Hybrid = lexical scoring + phrase boosting + topic/audience filtering,
pure Python over the in-memory store. The corpus is small and verified;
this beats pulling in FAISS/Chroma for dozens of chunks and keeps
retrieval in the low-millisecond range, far under the 200–300 ms target.

Score parts:
    token overlap (with synonym expansion)      — relevance
    exact phrase hits ("ai chess coach", …)      — brand/product terms
    topic hint match                             — intent alignment
    audience hint match                          — caller-type alignment
    verified-only filter + "unavailable" chunks  — honesty guards

"Unavailable" chunks (status="unavailable") hold ONLY the verified
statement that no verified data exists (e.g. plans.md) — they rank like
normal chunks so pricing questions retrieve the honest answer, and they
never carry invented facts.
"""

from __future__ import annotations

import re

from .models import KnowledgeChunk, RetrievalHit
from .store import KnowledgeStore

_WORD_RE = re.compile(r"[a-zA-Z']+")

_STOP = {
    "a", "an", "the", "is", "are", "am", "i", "you", "we", "they",
    "it", "of", "in", "on", "at", "to", "for", "and", "or", "my",
    "me", "your", "do", "does", "did", "can", "could", "what", "how",
    "why", "when", "where", "which", "who", "tell", "about", "please",
    "there", "this", "that", "with", "have", "has",
}

# Brand/domain tokens occur in nearly every chunk — they identify the
# corpus, not the answer. They score low so informative tokens decide.
_BRAND_WEIGHT = {"zhatura": 0.2, "chess": 0.2}

# Query-side synonym expansion so "kid"/"cost"/"class" still hit
# "child"/"pricing"/"lesson" chunks.
_SYNONYMS = {
    "kid": ("child",), "kids": ("children", "child"), "son": ("child",),
    "daughter": ("child",), "child": ("kid", "student"),
    "children": ("child", "students"),
    "cost": ("price", "pricing"), "price": ("cost", "pricing", "plan"),
    "fee": ("price", "pricing"), "fees": ("price", "pricing"),
    "much": ("cost",), "package": ("plan", "subscription"),
    "plans": ("plan", "subscription"), "subscription": ("plan",),
    "packages": ("package", "plan"),
    "class": ("lesson", "session"), "classes": ("lesson", "session"),
    "session": ("lesson",), "sessions": ("lesson",),
    "teacher": ("coach",), "trainer": ("coach",),
    "school": ("academy",), "organisation": ("organization",),
    "organization": ("academy",), "institute": ("academy",),
    "sign": ("login",), "log": ("login",), "password": ("login",),
    "track": ("progress", "tracking"), "tracking": ("progress",),
    "analytics": ("analysis",), "review": ("analysis",),
    "coaching": ("coach", "ai"), "coaches": ("coach",),
    "student": ("children", "child"), "students": ("student",),
}

# Exact phrases worth a bonus when present in both query and chunk.
_PHRASES = (
    "ai chess coach", "chess coach", "parent dashboard",
    "coach dashboard", "student dashboard", "chess academy",
    "game analysis", "progress", "lesson", "session",
)

# Native-script hints → latin retrieval tokens. Phone callers speak
# product terms in their own script ("பேரண்ட் டேஷ்போர்டு"; "చెస్ కోచ్")
# and saaras keeps the script, so without these the retriever sees an
# empty token set and wrongly reports "no verified information".
_NATIVE_HINTS = [
    ("சதுரங்க", ["chess"]), ("செஸ்", ["chess"]),
    ("చెస్", ["chess"]), ("చదరంగం", ["chess"]),
    ("चेस", ["chess"]), ("शतरंज", ["chess"]),
    ("கோச்", ["coach"]), ("కోచ్", ["coach"]), ("कोच", ["coach"]),
    ("பயிற்சியாளர்", ["coach"]),
    ("ஏஐ", ["ai"]), ("ఏఐ", ["ai"]), ("एआई", ["ai"]),
    ("டாஷ்போர்டு", ["dashboard"]), ("டேஷ்போர்டு", ["dashboard"]),
    ("டேஷ்போர்டி", ["dashboard"]), ("டாஷ்போர்டி", ["dashboard"]),
    ("డ్యాష్", ["dashboard"]), ("डैशबोर्ड", ["dashboard"]),
    ("பேரண்ட்", ["parent"]), ("பெற்றோர்", ["parent"]),
    ("పేరెంట్", ["parent"]), ("తల్లిదండ్రులు", ["parent"]),
    ("माता", ["parent"]), ("पिता", ["parent"]),
    ("குழந்தை", ["child"]), ("பிள்ளை", ["child"]),
    ("పిల్ల", ["child"]), ("बच्च", ["child"]),
    ("மாணவர்", ["student"]), ("విద్యార్థి", ["student"]),
    ("छात्र", ["student"]),
    ("பாடம்", ["lesson"]), ("செஷன்", ["session"]),
    ("పాఠం", ["lesson"]), ("సెషన్", ["session"]),
    ("पाठ", ["lesson"]), ("सेशन", ["session"]),
    ("கட்டணம்", ["price"]), ("விலை", ["price"]),
    ("கீమத்", ["price"]), ("कीमत", ["price"]), ("कितना", ["price"]),
    ("ధര", ["price"]), ("பிளான்", ["plan"]), ("प्लान", ["plan"]),
    ("ప్లాన్", ["plan"]), ("सब्सक्रिप्शन", ["subscription"]),
    ("சப்ஸ்கிரிப்ஷன்", ["subscription"]),
    ("ప్రोग्रెస్", ["progress"]), ("முன்னேற்றம்", ["progress"]),
    ("பஸில்", ["puzzle"]), ("अकादमी", ["academy"]),
    ("அகாடமி", ["academy"]), ("అకాడమీ", ["academy"]),
]

_TOPIC_BOOST = 0.9
_AUDIENCE_BOOST = 0.5
_PHRASE_BOOST = 0.4


def _tokens(text: str) -> "set[str]":
    out = set()
    for word in _WORD_RE.findall(text.lower()):
        if word in _STOP:
            continue
        out.add(word)
        out.update(_SYNONYMS.get(word, ()))
    lowered = text.lower()
    for native, latins in _NATIVE_HINTS:
        if native in lowered or native in text:
            out.update(latins)
    return out


def _weight(token: str) -> float:
    return _BRAND_WEIGHT.get(token, 1.0)


def _norm(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


class Retriever:
    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._index: "list[tuple[KnowledgeChunk, set[str], set[str], str]]" = []
        self.rebuild()

    def rebuild(self) -> None:
        """Re-tokenize every chunk (title separately from title+content).
        Called on load and after a knowledge rebuild."""
        self._index = [
            (c, _tokens(c.title), _tokens(c.title + " " + c.content),
             (c.title + " " + c.content).lower())
            for c in self.store.all()
        ]

    def retrieve(self, query: str, topic: "str | None" = None,
                 audience: "str | None" = None,
                 top_k: int = 4) -> "list[RetrievalHit]":
        q_tokens = _tokens(query)
        q_informative = q_tokens - set(_BRAND_WEIGHT)
        q_lower = query.lower()
        q_norm = _norm(query)
        hits: "list[RetrievalHit]" = []
        for chunk, c_title_tokens, c_tokens, c_lower in self._index:
            if not chunk.verified:
                continue                # never ground on unverified data
            score = sum(_weight(t) for t in q_tokens & c_tokens)
            # informative query tokens found in the chunk TITLE are a
            # strong signal (FAQ "What is Zhatura?" ↔ title match)
            for t in q_informative:
                if t in c_title_tokens:
                    score += 1.0
            if "zhatura" in c_title_tokens:
                score += 0.5 if "zhatura" in q_tokens else 0.0
            if q_norm and q_norm == _norm(chunk.title):
                score += 2.0
            for phrase in _PHRASES:
                if phrase in q_lower and phrase in c_lower:
                    score += _PHRASE_BOOST
            if topic and chunk.topic == topic:
                score += _TOPIC_BOOST
            if audience and audience in chunk.audience.split(","):
                score += _AUDIENCE_BOOST
            if chunk.priority:
                score += 0.1 * chunk.priority
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score))
        hits.sort(key=lambda h: (-h.score, h.chunk.id))
        return hits[:top_k]
