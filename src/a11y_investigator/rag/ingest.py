"""Index official docs (and, from T09, project policies) into Chroma (SERVICE_MVP.md 6.6).

MVP policy: always rebuild a collection from scratch.

Usage:
    python -m a11y_investigator.rag.ingest            # official docs
    python -m a11y_investigator.rag.ingest --dry-run  # build chunks only, no embedding calls
"""
from __future__ import annotations

import argparse
import time
from collections import Counter

from a11y_investigator.config import settings
from a11y_investigator.rag.chunker import official_chunks
from a11y_investigator.rag.metadata import Chunk
from a11y_investigator.rag.store import get_collection

BATCH_SIZE = 32


def rebuild_collection(name: str, chunks: list[Chunk]) -> int:
    """Drop and recreate `name`, then add all chunks. Returns the stored record count."""
    get_collection(name).delete_collection()
    store = get_collection(name)
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start : start + BATCH_SIZE]
        store.add_texts(
            texts=[c.text for c in batch],
            metadatas=[c.metadata.to_chroma() for c in batch],
            ids=[c.id for c in batch],
        )
    return store._collection.count()


def ingest_official(dry_run: bool = False) -> int:
    chunks = official_chunks()
    counts = Counter(c.metadata.source_type for c in chunks)
    print(f"official chunks: {len(chunks)} {dict(counts)}")
    if dry_run:
        return len(chunks)
    started = time.monotonic()
    stored = rebuild_collection(settings.official_collection, chunks)
    print(f"indexed {stored} records into '{settings.official_collection}' in {time.monotonic() - started:.1f}s")
    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="build chunks without embedding")
    args = parser.parse_args()
    ingest_official(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
