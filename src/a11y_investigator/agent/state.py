"""LangGraph state (SERVICE_MVP.md 7.1).

Nested results are stored as plain dicts (`model_dump()`) so the state stays
JSON-serializable for tracing.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from a11y_investigator.schemas.analyzer import CodeType, TargetLevel


class AnalysisState(TypedDict, total=False):
    # Input
    raw_input: str
    user_request: str
    input_code: str
    code_type: CodeType
    project_id: str | None
    target_level: TargetLevel
    component_hint: list[str] | None

    # Analysis
    static_result: dict[str, Any]  # AnalyzerResult
    official_documents: list[dict[str, Any]]
    policy_documents: list[dict[str, Any]]

    # Decision
    diagnosis: dict[str, Any]  # DiagnosisOutput, later FindingResult list after decide
    needs_improvement: bool

    # Fix loop
    improved_code: str | None
    revalidation_result: dict[str, Any] | None  # ValidationResult
    retry_count: int

    # Common
    report: dict[str, Any] | None  # DiagnosisReport
    errors: Annotated[list[str], operator.add]  # reducer: appended, never overwritten
    trace_id: str
