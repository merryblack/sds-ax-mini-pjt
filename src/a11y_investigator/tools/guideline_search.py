"""Guideline lookup tools (SERVICE_MVP.md 6.5, 4.2).

Plain functions used by the `retrieve` node; in P1 they are also exposed as
ReAct agent tools.
"""
from __future__ import annotations

from a11y_investigator.rag.retriever import RetrievedDoc, Retriever, to_doc

_default = Retriever()


def get_wcag_criterion(sc: str, retriever: Retriever | None = None) -> list[RetrievedDoc]:
    """Exact lookup of one success criterion: the SC text and its Understanding intent.

    Returns [] for an SC that is not indexed (e.g. a hallucinated number).
    """
    r = retriever or _default
    return r.exact_lookup([f"wcag-{sc}", f"understanding-{sc}-intent"])


def search_guidelines(
    query: str, k: int = 5, source_type: str | None = None, retriever: Retriever | None = None
) -> list[RetrievedDoc]:
    """Semantic search over official documents. Write `query` in English (documents are English)."""
    r = retriever or _default
    hits = r.official_store.similarity_search_with_score(
        query, k=k, filter={"source_type": source_type} if source_type else None
    )
    return [to_doc(d.page_content, d.metadata, "vector", float(s)) for d, s in hits]


def is_indexed_sc(sc: str, retriever: Retriever | None = None) -> bool:
    """True if `wcag-<sc>` exists in the index (used to reject made-up WCAG numbers)."""
    r = retriever or _default
    return bool(r.official_store.get(ids=[f"wcag-{sc}"])["ids"])
