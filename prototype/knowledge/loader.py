"""Zhatura AI Customer Care — knowledge ingestion (Phase 5).

Loads Markdown / JSON / plain-text source files into KnowledgeChunks.

Markdown convention (see knowledge/sources/*.md):

    ---
    id: zhatura_overview
    topic: overview
    audience: general
    verified: true
    last_updated: 2026-09-22
    provenance: README.md + system prompt
    ---
    # Doc Title
    ## Section heading
    Section body — becomes ONE chunk; chunk id = "<doc id>#<slug>".

Rules: semantic chunks (one per `##`/`###` section), section titles and
doc metadata preserved, tiny fragments (< 30 chars) merged into the
previous chunk, nothing is silently dropped.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .models import KnowledgeChunk

logger = logging.getLogger(__name__)

MIN_CHUNK_CHARS = 30        # below this, merge into the previous chunk

_META_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_meta_block(text: str) -> "tuple[dict, str]":
    """Split a leading ``--- key: value ---`` block from the body."""
    m = _META_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()
    return meta, text[m.end():]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _meta_bool(meta: dict, key: str, default: bool = True) -> bool:
    raw = (meta.get(key) or "").lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def load_markdown(path: Path) -> "list[KnowledgeChunk]":
    """One document → its section chunks, metadata attached."""
    text = path.read_text(encoding="utf-8")
    meta, body = parse_meta_block(text)
    doc_id = meta.get("id") or path.stem
    doc_topic = meta.get("topic") or "general"
    doc_audience = meta.get("audience") or "general"
    source_type = meta.get("source_type") or "approved_internal"
    verified = _meta_bool(meta, "verified", True)
    last_updated = meta.get("last_updated", "")
    status = meta.get("status", "available")
    tags = tuple(t.strip() for t in (meta.get("tags") or "").split(",")
                 if t.strip())
    provenance = meta.get("provenance", "")
    if provenance:
        tags = tags + (f"provenance:{provenance}",)

    sections: "list[tuple[str, list[str]]]" = []
    current_title, current_lines = "", []
    for line in body.splitlines():
        hm = _HEADING_RE.match(line.strip())
        if hm:
            if current_lines or current_title:
                sections.append((current_title, current_lines))
            current_title = hm.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections.append((current_title, current_lines))

    chunks: "list[KnowledgeChunk]" = []
    for title, lines in sections:
        content = "\n".join(lines).strip()
        # strip markdown emphasis the caller would otherwise hear
        content = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
        content = re.sub(r"^[-*]\s+", "", content, flags=re.MULTILINE)
        if not content:
            # a heading with no body (e.g. the doc-level "# Title")
            # carries no retrievable information — skip it
            continue
        if len(content) < MIN_CHUNK_CHARS and chunks:
            # too small to stand alone — merge into previous chunk
            prev = chunks[-1]
            merged = (prev.content + "\n" + (title + ". " if title else "")
                      + content).strip()
            chunks[-1] = KnowledgeChunk(
                id=prev.id, title=prev.title, topic=prev.topic,
                audience=prev.audience, content=merged,
                source=prev.source, section=prev.section,
                source_type=prev.source_type, verified=prev.verified,
                tags=prev.tags, language=prev.language,
                last_updated=prev.last_updated, priority=prev.priority,
                status=prev.status)
            continue
        section = title or doc_id
        chunks.append(KnowledgeChunk(
            id=f"{doc_id}#{_slug(section)}",
            title=title or doc_id.replace("_", " ").title(),
            topic=doc_topic,
            audience=doc_audience,
            content=content,
            source=str(path),
            section=section,
            source_type=source_type,
            verified=verified,
            tags=tags,
            last_updated=last_updated,
            status=status,
        ))
    return chunks


def load_json(path: Path) -> "list[KnowledgeChunk]":
    """JSON array of chunk-shaped objects (id/title/topic/audience/…)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: JSON knowledge must be an array.")
    chunks = []
    for i, item in enumerate(data):
        chunks.append(KnowledgeChunk(
            id=item.get("id") or f"{path.stem}#{i}",
            title=item.get("title", ""),
            topic=item.get("topic", "general"),
            audience=item.get("audience", "general"),
            content=item.get("content", ""),
            source=str(path),
            section=item.get("section", ""),
            source_type=item.get("source_type", "approved_internal"),
            verified=bool(item.get("verified", True)),
            tags=tuple(item.get("tags", ())),
            last_updated=item.get("last_updated", ""),
            status=item.get("status", "available"),
        ))
    return chunks


def load_text(path: Path) -> "list[KnowledgeChunk]":
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [KnowledgeChunk(
        id=f"{path.stem}#body", title=path.stem.replace("_", " ").title(),
        topic="general", audience="general", content=content,
        source=str(path), source_type="approved_internal")]


_LOADERS = {".md": load_markdown, ".json": load_json, ".txt": load_text}


def load_sources(sources_dir: "str | Path") -> "list[KnowledgeChunk]":
    """Load every supported file in ``sources_dir`` (sorted, stable)."""
    directory = Path(sources_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Knowledge sources not found: {directory}")
    chunks: "list[KnowledgeChunk]" = []
    for path in sorted(directory.iterdir()):
        loader = _LOADERS.get(path.suffix.lower())
        if loader is None:
            continue
        loaded = loader(path)
        logger.debug("knowledge: %s → %d chunk(s)", path.name, len(loaded))
        chunks.extend(loaded)
    return chunks
