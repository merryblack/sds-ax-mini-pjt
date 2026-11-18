"""Evidence retrieval (SERVICE_MVP.md 6.5).

Order of operations:
1. Exact lookup by ID — WCAG SC from `wcag_refs`, APG sections from the APG
   patterns implied by rules and `component_hint`. No embedding call.
2. Vector search with English template queries built from the component hint,
   rule IDs, and analyzer messages (no LLM). Fills the remaining official slots.
3. Project policies (when `project_id` is given): policies whose `applies_to`
   overlaps the relevant components; vector search only when no component is known.

Caps: official <= settings.max_official_docs (6), policies <= settings.max_policy_docs (4).
At most EXACT_BUDGET official slots go to exact lookup so vector results always get room.
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

from langchain_core.documents import Document
from pydantic import BaseModel, Field

from a11y_investigator.config import settings
from a11y_investigator.rag.metadata import from_chroma
from a11y_investigator.schemas.analyzer import AnalyzerResult
from a11y_investigator.tools.rule_mapping import APG_PATTERNS, apg_patterns_of, wcag_refs_of

EXACT_BUDGET = 4
VECTOR_K = 4
MAX_QUERIES = 3

Via = Literal["exact", "vector", "policy"]


class RetrievalError(RuntimeError):
    pass


class RetrievedDoc(BaseModel):
    document_id: str
    text: str
    source_type: str
    title: str
    section: str = ""
    source_url: str = ""
    component: str = ""
    wcag_sc: list[str] = Field(default_factory=list)
    project_id: str = ""
    score: float | None = None  # cosine distance (lower = closer); None for exact lookups
    via: Via


class RetrievalResult(BaseModel):
    official: list[RetrievedDoc] = Field(default_factory=list)
    policies: list[RetrievedDoc] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)  # for tracing

    @property
    def document_ids(self) -> set[str]:
        return {d.document_id for d in self.official + self.policies}


class VectorStore(Protocol):
    """The subset of langchain_chroma.Chroma used here (fakes implement it in tests)."""

    def get(self, ids: list[str] | None = None, where: dict | None = None) -> dict[str, Any]: ...

    def similarity_search_with_score(
        self, query: str, k: int = 4, filter: dict | None = None
    ) -> list[tuple[Document, float]]: ...


def to_doc(text: str, metadata: dict, via: Via, score: float | None = None) -> RetrievedDoc:
    meta = from_chroma(metadata)
    return RetrievedDoc(
        document_id=meta.document_id,
        text=text,
        source_type=meta.source_type,
        title=meta.title,
        section=meta.section,
        source_url=meta.source_url,
        component=meta.component,
        wcag_sc=meta.wcag_sc,
        project_id=meta.project_id,
        score=score,
        via=via,
    )


# ── Planning (pure functions) ───────────────────────────────


def relevant_patterns(result: AnalyzerResult, component_hint: list[str] | None) -> list[str]:
    found = set(component_hint or []) | set(apg_patterns_of(result))
    return [p for p in APG_PATTERNS if p in found]


def exact_ids(result: AnalyzerResult, component_hint: list[str] | None) -> list[str]:
    """Candidate IDs for exact lookup, most important first."""
    scs = wcag_refs_of(result)
    patterns = relevant_patterns(result, component_hint)
    ids = (
        [f"wcag-{sc}" for sc in scs]
        + [f"apg-{p}-keyboard" for p in patterns]
        + [f"apg-{p}-roles" for p in patterns]
        + [f"understanding-{sc}-intent" for sc in scs]
    )
    return list(dict.fromkeys(ids))


def build_queries(result: AnalyzerResult, component_hint: list[str] | None) -> list[str]:
    """English template queries (no LLM), one per distinct rule, at most MAX_QUERIES."""
    patterns = relevant_patterns(result, component_hint)
    component = patterns[0] if patterns else "UI component"
    queries: list[str] = []
    seen_rules: set[str] = set()
    for finding in result.findings:
        if finding.rule_id in seen_rules:
            continue
        seen_rules.add(finding.rule_id)
        rule = finding.rule_id.removeprefix("jsx-a11y/").replace("-", " ")
        queries.append(f"{component} accessibility {rule} {finding.message}")
        if len(queries) >= MAX_QUERIES:
            break
    if not queries:
        queries = [f"{p} keyboard interaction ARIA" for p in patterns[:MAX_QUERIES]] or [
            "UI component keyboard interaction ARIA"
        ]
    return queries


# ── Retriever ───────────────────────────────────────────────


class Retriever:
    def __init__(self, official_store: VectorStore | None = None, policy_store: VectorStore | None = None):
        self._official = official_store
        self._policy = policy_store

    @property
    def official_store(self) -> VectorStore:
        if self._official is None:
            self._official = _open(settings.official_collection)
        return self._official

    @property
    def policy_store(self) -> VectorStore:
        if self._policy is None:
            self._policy = _open(settings.policy_collection)
        return self._policy

    def exact_lookup(self, ids: list[str]) -> list[RetrievedDoc]:
        if not ids:
            return []
        got = self.official_store.get(ids=ids)
        by_id = {
            meta["document_id"]: to_doc(text, meta, "exact")
            for text, meta in zip(got["documents"], got["metadatas"])
        }
        return [by_id[i] for i in ids if i in by_id]  # keep priority order

    def vector_search(self, queries: list[str], exclude: set[str], limit: int) -> list[RetrievedDoc]:
        if limit <= 0:
            return []
        best: dict[str, RetrievedDoc] = {}
        for query in queries:
            for document, score in self.official_store.similarity_search_with_score(query, k=VECTOR_K):
                doc = to_doc(document.page_content, document.metadata, "vector", float(score))
                if doc.document_id in exclude:
                    continue
                current = best.get(doc.document_id)
                if current is None or doc.score < current.score:  # type: ignore[operator]
                    best[doc.document_id] = doc
        return sorted(best.values(), key=lambda d: d.score)[:limit]  # type: ignore[arg-type,return-value]

    def policy_search(self, project_id: str, patterns: list[str], queries: list[str]) -> list[RetrievedDoc]:
        cap = settings.max_policy_docs
        if patterns:
            got = self.policy_store.get(where={"project_id": project_id})
            docs = [to_doc(t, m, "policy") for t, m in zip(got["documents"], got["metadatas"])]

            def overlap(d: RetrievedDoc) -> int:
                return len(set(d.component.split(",")) & set(patterns))

            matched = [d for d in docs if overlap(d)]
            # more specific policies (fewer components) first, then by id for stability
            matched.sort(key=lambda d: (-overlap(d), len(d.component.split(",")), d.document_id))
            return matched[:cap]
        hits = self.policy_store.similarity_search_with_score(
            " ".join(queries), k=cap, filter={"project_id": project_id}
        )
        return [to_doc(d.page_content, d.metadata, "policy", float(s)) for d, s in hits]

    def retrieve(
        self,
        result: AnalyzerResult,
        component_hint: list[str] | None = None,
        project_id: str | None = None,
    ) -> RetrievalResult:
        """`result` should already have `wcag_refs` filled (rule_mapping.apply_mapping)."""
        cap = settings.max_official_docs
        exact = self.exact_lookup(exact_ids(result, component_hint))[: min(EXACT_BUDGET, cap)]
        queries = build_queries(result, component_hint)
        vector = self.vector_search(queries, {d.document_id for d in exact}, cap - len(exact))
        policies = (
            self.policy_search(project_id, relevant_patterns(result, component_hint), queries)
            if project_id
            else []
        )
        return RetrievalResult(official=exact + vector, policies=policies, queries=queries)


def _open(name: str) -> VectorStore:
    if not (settings.chroma_dir / "chroma.sqlite3").exists():
        raise RetrievalError("검색 인덱스가 없습니다. `python -m a11y_investigator.rag.ingest`를 먼저 실행하세요.")
    from a11y_investigator.rag.store import get_collection

    return get_collection(name)


def retrieve(
    result: AnalyzerResult, component_hint: list[str] | None = None, project_id: str | None = None
) -> RetrievalResult:
    return Retriever().retrieve(result, component_hint, project_id)
