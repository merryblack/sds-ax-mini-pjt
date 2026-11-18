"""T08: official document chunking and the Chroma index (SERVICE_MVP.md 6.1, 6.4, 6.6).

Chunk tests run offline on the committed knowledge/official files.
Index tests read the local Chroma store (no embedding calls) and are skipped if
`python -m a11y_investigator.rag.ingest` has not been run.
The search test calls Bedrock and only runs with `-m llm`.
"""
from __future__ import annotations

import pytest

from a11y_investigator.config import settings
from a11y_investigator.rag.chunker import CHUNK_SIZE, official_chunks
from a11y_investigator.rag.metadata import from_chroma
from a11y_investigator.tools.rule_mapping import all_mapped_sc


@pytest.fixture(scope="module")
def chunks():
    return official_chunks()


# ── Chunks (offline) ────────────────────────────────────────


def test_chunk_ids_unique_and_types_present(chunks) -> None:
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert {c.metadata.source_type for c in chunks} == {"wcag", "understanding", "technique", "apg"}


def test_every_mapped_sc_has_a_wcag_chunk(chunks) -> None:
    """Deferred from T07: every SC in rule-wcag-map.yaml exists in the indexed documents."""
    wcag_ids = {c.id for c in chunks if c.metadata.source_type == "wcag"}
    missing = {sc for sc in all_mapped_sc() if f"wcag-{sc}" not in wcag_ids}
    assert not missing, f"mapped SC without WCAG document: {sorted(missing)}"


def test_every_wcag_sc_has_understanding_intent(chunks) -> None:
    wcag_sc = {c.metadata.wcag_sc[0] for c in chunks if c.metadata.source_type == "wcag"}
    intents = {c.metadata.wcag_sc[0] for c in chunks if c.id.endswith("-intent")}
    assert wcag_sc == intents


def test_apg_sections_for_all_components(chunks) -> None:
    ids = {c.id for c in chunks}
    for pattern in ("button", "dialog", "tabs", "combobox"):
        for section in ("about", "keyboard", "roles"):
            assert f"apg-{pattern}-{section}" in ids


def test_chunk_size_bounded_and_text_readable(chunks) -> None:
    for c in chunks:
        header, _, body = c.text.partition("\n")
        assert header.startswith("[") and header.endswith("]")
        assert 0 < len(body) <= CHUNK_SIZE + 10
    sc = next(c for c in chunks if c.id == "wcag-2.1.1")
    assert "All functionality of the content is operable through a keyboard interface" in sc.text


def test_metadata_is_chroma_safe(chunks) -> None:
    for c in chunks:
        meta = c.metadata.to_chroma()
        assert all(isinstance(v, str) for v in meta.values())
        assert meta["source_url"].startswith("https://www.w3.org/")
        assert from_chroma(meta) == c.metadata


def test_technique_chunks_reference_selected_sc(chunks) -> None:
    sc_set = {c.metadata.wcag_sc[0] for c in chunks if c.metadata.source_type == "wcag"}
    for c in chunks:
        if c.metadata.source_type == "technique":
            assert c.metadata.wcag_sc and set(c.metadata.wcag_sc) <= sc_set


# ── Index (local Chroma, no embedding calls) ────────────────

needs_index = pytest.mark.skipif(
    not (settings.chroma_dir / "chroma.sqlite3").exists(), reason="run rag.ingest first"
)


@pytest.fixture(scope="module")
def store():
    from a11y_investigator.rag.store import get_collection

    return get_collection(settings.official_collection)


@needs_index
def test_index_matches_chunks(store, chunks) -> None:
    assert store._collection.count() == len(chunks)


@needs_index
def test_exact_lookup_by_document_id(store) -> None:
    result = store.get(ids=["wcag-2.1.1", "apg-dialog-keyboard"])
    assert sorted(result["ids"]) == ["apg-dialog-keyboard", "wcag-2.1.1"]


@needs_index
def test_all_mapped_sc_retrievable(store) -> None:
    wanted = [f"wcag-{sc}" for sc in all_mapped_sc()]
    assert sorted(store.get(ids=wanted)["ids"]) == sorted(wanted)


@needs_index
def test_metadata_filter_by_component(store) -> None:
    result = store.get(where={"$and": [{"source_type": "apg"}, {"component": "dialog"}]})
    assert result["ids"] and all(i.startswith("apg-dialog-") for i in result["ids"])


@needs_index
@pytest.mark.llm
def test_semantic_search_finds_keyboard_docs(store) -> None:
    query = "dialog keyboard interaction focus trap Escape"
    ids = [d.metadata["document_id"] for d in store.similarity_search(query, k=5)]
    assert any(i.startswith("apg-dialog-keyboard") or "2.1.2" in i for i in ids)
