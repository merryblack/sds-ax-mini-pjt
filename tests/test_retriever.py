"""T10: retriever (SPEC_MVP.md 6.5).

Most tests use an in-memory fake store (no Chroma, no Bedrock).
`-m llm` runs the M1 milestone check against the real index.
"""
from __future__ import annotations

import pytest
from langchain_core.documents import Document

from a11y_investigator.config import settings
from a11y_investigator.rag.metadata import ChunkMetadata
from a11y_investigator.rag.retriever import (
    Retriever,
    build_queries,
    exact_ids,
    relevant_patterns,
)
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.tools.guideline_search import get_wcag_criterion, is_indexed_sc
from a11y_investigator.tools.rule_mapping import apply_mapping

SCENARIO_A = apply_mapping(
    AnalyzerResult(
        parse_ok=True,
        findings=[
            StaticFinding(
                tool="eslint-jsx-a11y",
                rule_id="jsx-a11y/click-events-have-key-events",
                message="Visible, non-interactive elements with click handlers must have at least one keyboard listener.",
                line=2, element="div",
            ),
            StaticFinding(
                tool="eslint-jsx-a11y",
                rule_id="jsx-a11y/no-static-element-interactions",
                message="Avoid non-native interactive elements.",
                line=2, element="div",
            ),
        ],
    )
)
EMPTY = AnalyzerResult(parse_ok=True)


def meta(doc_id: str, source_type: str = "wcag", **kw) -> dict:
    return ChunkMetadata(
        document_id=doc_id, source_type=source_type, source_name="s", title=doc_id, **kw
    ).to_chroma()


class FakeStore:
    """Implements the VectorStore protocol over a list of (id, metadata)."""

    def __init__(self, records: list[dict], ranking: list[str] | None = None):
        self.records = {m["document_id"]: m for m in records}
        self.ranking = ranking or list(self.records)
        self.queries: list[str] = []

    def get(self, ids=None, where=None):
        items = [self.records[i] for i in ids if i in self.records] if ids else list(self.records.values())
        if where:
            items = [m for m in items if all(m.get(k) == v for k, v in where.items())]
        return {"ids": [m["document_id"] for m in items],
                "documents": [f"text of {m['document_id']}" for m in items],
                "metadatas": items}

    def similarity_search_with_score(self, query, k=4, filter=None):
        self.queries.append(query)
        out = []
        for rank, doc_id in enumerate(self.ranking):
            m = self.records[doc_id]
            if filter and any(m.get(key) != v for key, v in filter.items()):
                continue
            out.append((Document(page_content=f"text of {doc_id}", metadata=m), 0.3 + rank * 0.05))
        return out[:k]


OFFICIAL = FakeStore(
    [meta(i) for i in ["wcag-2.1.1", "wcag-4.1.2"]]
    + [meta(i, "understanding") for i in ["understanding-2.1.1-intent", "understanding-4.1.2-intent"]]
    + [meta(i, "apg", component="button") for i in ["apg-button-keyboard", "apg-button-roles", "apg-button-about"]]
    + [meta(i, "apg", component="dialog") for i in ["apg-dialog-keyboard", "apg-dialog-roles"]]
    + [meta(i, "technique") for i in ["technique-SCR35-description", "technique-ARIA14-description"]],
    ranking=["technique-SCR35-description", "wcag-2.1.1", "apg-button-about", "technique-ARIA14-description"],
)
POLICIES = FakeStore([
    meta("demo-ds-btn-001", "project_policy", project_id="demo-ds", component="button"),
    meta("demo-ds-icon-001", "project_policy", project_id="demo-ds", component="button"),
    meta("demo-ds-dialog-001", "project_policy", project_id="demo-ds", component="dialog"),
    meta("demo-ds-focus-001", "project_policy", project_id="demo-ds", component="button,dialog,tabs,combobox"),
    meta("other-btn-001", "project_policy", project_id="other", component="button"),
])


# ── Planning ────────────────────────────────────────────────


def test_exact_ids_order_for_scenario_a() -> None:
    assert exact_ids(SCENARIO_A, ["button"]) == [
        "wcag-2.1.1", "wcag-4.1.2", "apg-button-keyboard", "apg-button-roles",
        "understanding-2.1.1-intent", "understanding-4.1.2-intent",
    ]


def test_patterns_from_hint_when_no_findings() -> None:
    assert relevant_patterns(EMPTY, ["dialog"]) == ["dialog"]
    assert exact_ids(EMPTY, ["dialog"]) == ["apg-dialog-keyboard", "apg-dialog-roles"]


def test_queries_are_english_templates() -> None:
    queries = build_queries(SCENARIO_A, ["button"])
    assert len(queries) == 2
    assert queries[0].startswith("button accessibility click events have key events Visible")
    assert build_queries(EMPTY, ["dialog", "tabs"]) == [
        "dialog keyboard interaction ARIA", "tabs keyboard interaction ARIA"
    ]
    assert build_queries(EMPTY, None) == ["UI component keyboard interaction ARIA"]


# ── Retrieval with fake stores ──────────────────────────────


def test_scenario_a_exact_then_vector_with_caps() -> None:
    result = Retriever(OFFICIAL, POLICIES).retrieve(SCENARIO_A, ["button"])
    ids = [d.document_id for d in result.official]
    assert ids[:4] == ["wcag-2.1.1", "wcag-4.1.2", "apg-button-keyboard", "apg-button-roles"]
    assert all(d.via == "exact" for d in result.official[:4])
    # vector fills the remaining 2 slots, skipping docs already found exactly
    assert ids[4:] == ["technique-SCR35-description", "apg-button-about"]
    assert len(ids) == settings.max_official_docs
    assert result.policies == []


def test_missing_ids_are_skipped() -> None:
    result = Retriever(OFFICIAL, POLICIES).retrieve(EMPTY, ["combobox"])
    assert all(d.via == "vector" for d in result.official)  # no apg-combobox-* in the fake store


def test_policies_by_component_overlap() -> None:
    result = Retriever(OFFICIAL, POLICIES).retrieve(SCENARIO_A, ["button"], project_id="demo-ds")
    assert [d.document_id for d in result.policies] == [
        "demo-ds-btn-001", "demo-ds-icon-001", "demo-ds-focus-001"
    ]
    dialog = Retriever(OFFICIAL, POLICIES).retrieve(EMPTY, ["dialog"], project_id="demo-ds")
    assert [d.document_id for d in dialog.policies] == ["demo-ds-dialog-001", "demo-ds-focus-001"]


def test_policies_never_cross_projects() -> None:
    result = Retriever(OFFICIAL, POLICIES).retrieve(SCENARIO_A, ["button"], project_id="demo-ds")
    assert all(d.project_id == "demo-ds" for d in result.policies)
    unknown = Retriever(OFFICIAL, POLICIES).retrieve(SCENARIO_A, ["button"], project_id="nope")
    assert unknown.policies == []


def test_policy_vector_fallback_without_component() -> None:
    result = Retriever(OFFICIAL, POLICIES).retrieve(EMPTY, None, project_id="demo-ds")
    assert result.policies and all(d.project_id == "demo-ds" for d in result.policies)


def test_get_wcag_criterion_with_fake() -> None:
    r = Retriever(OFFICIAL, POLICIES)
    assert [d.document_id for d in get_wcag_criterion("2.1.1", r)] == [
        "wcag-2.1.1", "understanding-2.1.1-intent"
    ]
    assert get_wcag_criterion("9.9.9", r) == []
    assert is_indexed_sc("4.1.2", r) and not is_indexed_sc("9.9.9", r)


# ── Real index ──────────────────────────────────────────────

needs_index = pytest.mark.skipif(
    not (settings.chroma_dir / "chroma.sqlite3").exists(), reason="run rag.ingest first"
)


@needs_index
def test_real_exact_lookup_no_embedding() -> None:
    docs = get_wcag_criterion("2.1.1", Retriever())
    assert docs[0].source_url == "https://www.w3.org/TR/WCAG22/#keyboard"


@needs_index
@pytest.mark.llm
def test_m1_scenario_a_retrieves_wcag_and_apg_button() -> None:
    """M1 milestone: Scenario A's analysis retrieves WCAG 2.1.1 and APG Button."""
    result = Retriever().retrieve(SCENARIO_A, ["button"], project_id="demo-ds")
    ids = [d.document_id for d in result.official]
    assert "wcag-2.1.1" in ids
    assert any(i.startswith("apg-button-") for i in ids)
    assert len(ids) <= settings.max_official_docs
    assert "demo-ds-btn-001" in [d.document_id for d in result.policies]
