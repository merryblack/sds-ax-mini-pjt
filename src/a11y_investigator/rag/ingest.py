"""Index official docs and project policies into Chroma (SERVICE_MVP.md 6.6).

MVP policy: always rebuild a collection from scratch.

Usage:
    python -m a11y_investigator.rag.ingest              # official docs + project policies
    python -m a11y_investigator.rag.ingest --policies   # project policies only (fast)
    python -m a11y_investigator.rag.ingest --official   # official docs only
    python -m a11y_investigator.rag.ingest --dry-run    # build chunks only, no embedding calls
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from a11y_investigator.config import settings
from a11y_investigator.rag.chunker import official_chunks
from a11y_investigator.rag.metadata import Chunk
from a11y_investigator.rag.store import get_collection
from a11y_investigator.tools.policy_lookup import list_projects, policy_chunks

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


def _ingest(name: str, chunks: list[Chunk], label: str, dry_run: bool) -> int:
    counts = Counter(c.metadata.source_type for c in chunks)
    print(f"{label} chunks: {len(chunks)} {dict(counts)}")
    if dry_run:
        return len(chunks)
    started = time.monotonic()
    stored = rebuild_collection(name, chunks)
    print(f"indexed {stored} records into '{name}' in {time.monotonic() - started:.1f}s")
    return stored


def ingest_official(dry_run: bool = False) -> int:
    return _ingest(settings.official_collection, official_chunks(), "official", dry_run)


def ingest_policies(dry_run: bool = False) -> int:
    stored = _ingest(settings.policy_collection, policy_chunks(), "policy", dry_run)
    if not dry_run:
        save_policy_hashes({pid: project_policy_hash(pid) for pid in list_projects()})
    return stored


# ── Policy auto-reindex (SERVICE_MVP.md 6.2) ────────────────

POLICY_HASH_FILE_NAME = "policy-hashes.json"


def _hash_file(path: Path | None) -> Path:
    return path or settings.chroma_dir / POLICY_HASH_FILE_NAME


def project_policy_hash(project_id: str, root: Path | None = None) -> str:
    """sha256 over project.yaml and every policy file (names + contents), in a stable order."""
    folder = (root or settings.policies_dir) / project_id
    digest = hashlib.sha256()
    for path in sorted([folder / "project.yaml", *folder.glob("*.md")]):
        if path.is_file():
            digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def load_policy_hashes(path: Path | None = None) -> dict[str, str]:
    try:
        return json.loads(_hash_file(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_policy_hashes(hashes: dict[str, str], path: Path | None = None) -> None:
    file = _hash_file(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(hashes, indent=2, sort_keys=True), encoding="utf-8")


def reindex_project_policies(project_id: str, root: Path | None = None) -> int:
    """Replace only `project_id`'s records in the policy collection."""
    chunks = [c for c in policy_chunks(root) if c.metadata.project_id == project_id]
    store = get_collection(settings.policy_collection)
    store._collection.delete(where={"project_id": project_id})
    if chunks:
        store.add_texts(
            texts=[c.text for c in chunks],
            metadatas=[c.metadata.to_chroma() for c in chunks],
            ids=[c.id for c in chunks],
        )
    return len(chunks)


def ensure_project_policies_current(
    project_id: str,
    root: Path | None = None,
    hash_file: Path | None = None,
    reindex: Callable[[str], object] | None = None,
) -> bool:
    """Reindex `project_id`'s policies if their files changed since the last indexing.

    Returns True when a reindex happened. Users can edit policy files and analyze
    right away without running `ingest --policies`.
    """
    current = project_policy_hash(project_id, root)
    hashes = load_policy_hashes(hash_file)
    if hashes.get(project_id) == current:
        return False
    (reindex or (lambda pid: reindex_project_policies(pid, root)))(project_id)
    hashes[project_id] = current
    save_policy_hashes(hashes, hash_file)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--official", action="store_true", help="index official docs only")
    parser.add_argument("--policies", action="store_true", help="index project policies only")
    parser.add_argument("--dry-run", action="store_true", help="build chunks without embedding")
    args = parser.parse_args()
    both = not args.official and not args.policies
    if args.official or both:
        ingest_official(dry_run=args.dry_run)
    if args.policies or both:
        ingest_policies(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
