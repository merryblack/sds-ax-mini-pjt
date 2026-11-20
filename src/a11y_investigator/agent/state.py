"""LangGraph state (SPEC_MVP.md 7.1).

Nested results are stored as plain dicts (`model_dump()`) so the state stays
JSON-serializable for tracing.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from a11y_investigator.schemas.analyzer import CodeType, TargetLevel


class AnalysisState(TypedDict, total=False):
    # Input (set by the caller)
    raw_input: str
    file_code: str | None
    project_id: str | None
    level_override: TargetLevel | None  # CLI --level
    trace_id: str

    # parse_input
    user_request: str
    input_code: str
    code_type: CodeType
    requested_level: TargetLevel | None  # level named in the request text
    target_level: TargetLevel  # resolved: --level > request > project > AA
    component_hint: list[str] | None
    component_mapping: dict[str, str]

    # analyze / map_rules
    static_result: dict[str, Any]  # AnalyzerResult (wcag_refs filled after map_rules)

    # retrieve
    official_documents: list[dict[str, Any]]  # RetrievedDoc
    policy_documents: list[dict[str, Any]]
    retrieval_queries: list[str]
    policies_reindexed: bool

    # diagnose / decide
    diagnosis: dict[str, Any]  # DiagnosisOutput (raw LLM output)
    decision: dict[str, Any]  # Decision (after guardrails)
    needs_improvement: bool

    # generate_fix / revalidate loop
    improved_code: str | None
    fix_changes: list[dict[str, Any]]  # CodeChange
    revalidation_result: dict[str, Any] | None  # ValidationResult
    after_static_result: dict[str, Any] | None  # AnalyzerResult of the improved code
    retry_count: int  # number of failed attempts so far

    # Failure that ends the run early: {"stage": ..., "code": ..., "message": ...}
    failure: dict[str, str] | None

    # Output
    report: dict[str, Any] | None  # DiagnosisReport

    # Accumulated (reducers: appended, never overwritten)
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
