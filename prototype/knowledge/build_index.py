"""Zhatura AI Customer Care — knowledge build/validate CLI (Phase 5).

    python -m knowledge.build_index [sources_dir]

Reloads every knowledge source, rebuilds the in-memory index and runs
the validator. Exit 0 = clean; exit 1 = validation issues (printed).

The index itself is rebuilt in-process on every server start
(KnowledgeService.__init__), and live reload is
`KnowledgeService.reload()` — this command is the offline "did my
edit parse cleanly?" gate. After changing knowledge files, restart the
server process (or call reload()) to pick them up.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge.loader import load_sources  # noqa: E402
from knowledge.validate import validate_chunks  # noqa: E402


def main(argv: "list[str]") -> int:
    sources = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).resolve().parent / "sources")
    chunks = load_sources(sources)
    docs = sorted({c.source.rsplit("/", 1)[-1] for c in chunks})
    topics = sorted({c.topic for c in chunks})
    print(f"Sources dir : {sources}")
    print(f"Documents   : {len(docs)} ({', '.join(docs)})")
    print(f"Chunks      : {len(chunks)}")
    print(f"Topics      : {', '.join(topics)}")
    print(f"Verified    : {sum(1 for c in chunks if c.verified)}/"
          f"{len(chunks)}")
    issues = validate_chunks(chunks)
    if issues:
        print("\nVALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("\nVALIDATION: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
