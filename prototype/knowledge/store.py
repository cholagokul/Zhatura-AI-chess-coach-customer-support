"""Zhatura AI Customer Care — in-memory knowledge store (Phase 5).

Deliberately simple: the verified corpus is small (dozens of chunks),
so a flat list with topic/audience indexes beats any external index.
Rebuild = reload + re-register (see knowledge/build_index.py).
"""

from __future__ import annotations

from collections import defaultdict

from .models import KnowledgeChunk


class KnowledgeStore:
    def __init__(self):
        self._chunks: "list[KnowledgeChunk]" = []
        self._by_topic: "dict[str, list[KnowledgeChunk]]" = defaultdict(list)

    def add(self, chunk: KnowledgeChunk) -> None:
        if any(c.id == chunk.id for c in self._chunks):
            raise ValueError(f"Duplicate knowledge chunk id: {chunk.id}")
        self._chunks.append(chunk)
        self._by_topic[chunk.topic].append(chunk)

    def extend(self, chunks) -> None:
        for c in chunks:
            self.add(c)

    def all(self) -> "list[KnowledgeChunk]":
        return list(self._chunks)

    def by_topic(self, topic: str) -> "list[KnowledgeChunk]":
        return list(self._by_topic.get(topic, ()))

    def topics(self) -> "list[str]":
        return sorted(self._by_topic)

    def __len__(self) -> int:
        return len(self._chunks)
