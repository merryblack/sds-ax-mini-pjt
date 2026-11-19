"""LangGraph workflow and report assembly (SERVICE_MVP.md 4장, 3.2, 7.2).

parse_input -> analyze -> map_rules -> retrieve -> diagnose -> decide
    -> (needs_improvement) generate_fix -> revalidate -> (failed & retries left) generate_fix
    -> report
Any failure in parse_input / analyze / diagnose / generate_fix jumps to report.
"""
from __future__ import annotations

import uuid
from functools import lru_cache, partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from a11y_investigator.agent import nodes
from a11y_investigator.agent.decision import Decision
from a11y_investigator.agent.state import AnalysisState
from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import TargetLevel
from a11y_investigator.schemas.diagnosis import (
    CodeChange,
    DiagnosisReport,
    DocumentEvidence,
    ValidationResult,
)

SCOPE_NOTE = "자동 검사(정적 분석·문서 근거) 범위 안의 결과이며, 접근성 완전 준수를 의미하지 않습니다."
UNVERIFIED_WARNING = "⚠ 아래 코드는 재검증을 통과하지 못한 검증되지 않은 코드입니다. 그대로 적용하지 마세요."


# ── Report ──────────────────────────────────────────────────


def _sources(state: AnalysisState, decision: Decision) -> dict[str, str]:
    urls = {
        d["document_id"]: d.get("source_url", "")
        for d in state.get("official_documents", []) + state.get("policy_documents", [])
    }
    cited = {
        ev.document_id
        for f in decision.findings
        for ev in f.evidence
        if isinstance(ev, DocumentEvidence)
    }
    return {doc_id: urls[doc_id] for doc_id in sorted(cited) if doc_id in urls}


def _counts(decision: Decision) -> str:
    by_status = {s: sum(f.status == s for f in decision.findings) for s in ("confirmed", "suspected", "manual_review")}
    return (
        f"문제 {len(decision.findings)}건(확정 {by_status['confirmed']}, 추정 {by_status['suspected']}, "
        f"수동 확인 {by_status['manual_review']})"
    )


def build_report(state: AnalysisState) -> DiagnosisReport:
    failure = state.get("failure")
    static = state.get("static_result") or {}
    base: dict[str, Any] = {
        "code_type": state.get("code_type"),
        "target_level": state.get("target_level", settings.default_target_level),
        "project_id": state.get("project_id"),
        "model": settings.chat_model_id,
        "index_version": settings.index_version,
        "analyzer_versions": static.get("analyzer_versions", {}),
        "trace_id": state.get("trace_id", ""),
    }

    if failure and failure["stage"] in ("parse_input", "analyze", "diagnose"):
        return DiagnosisReport(
            **base, outcome="analysis_failed", error=failure["message"],
            overall_summary=f"분석하지 못했습니다: {failure['message']}",
        )

    decision = Decision.model_validate(state["decision"])
    common: dict[str, Any] = {
        **base,
        "findings": decision.findings,
        "policy_assessments": decision.policy_assessments,
        "manual_checks": decision.manual_checks,
        "sources": _sources(state, decision),
    }
    parse_note = "" if static.get("parse_ok", True) else " 코드 파싱에 실패해 자동 수정은 하지 않았습니다."

    if not state.get("needs_improvement"):
        outcome = "no_issue_detected" if not decision.findings else "no_change_needed"
        summary = (
            "자동 검사에서 문제를 발견하지 못했습니다. 원본 코드를 유지합니다."
            if outcome == "no_issue_detected"
            else f"{_counts(decision)}. 자동 수정 대상이 없어 원본 코드를 유지합니다."
        )
        return DiagnosisReport(**common, outcome=outcome, overall_summary=f"{summary}{parse_note} {SCOPE_NOTE}")

    changes = [CodeChange.model_validate(c) for c in state.get("fix_changes", [])]
    if failure:  # generate_fix failed (e.g. Bedrock error)
        return DiagnosisReport(
            **common, outcome="fix_failed", changes=changes, error=failure["message"],
            improved_code=state.get("improved_code"),
            overall_summary=f"{_counts(decision)}. 수정 코드를 생성하지 못했습니다: {failure['message']}",
        )

    validation = ValidationResult.model_validate(state["revalidation_result"])
    targets = len(decision.fix_targets)
    if validation.status == "passed":
        summary = (
            f"{_counts(decision)}. 수정 대상 {targets}건을 고쳤고 재검증을 통과했습니다"
            f"(시도 {validation.attempts}회, 변경 {validation.changed_lines}줄). {SCOPE_NOTE}"
        )
        return DiagnosisReport(
            **common, outcome="improved", improved_code=state.get("improved_code"),
            changes=changes, validation=validation, overall_summary=summary,
        )
    summary = (
        f"{UNVERIFIED_WARNING} {_counts(decision)}. 수정 대상 {targets}건에 대해 "
        f"{validation.attempts}회 시도했지만 재검증을 통과하지 못했습니다. {SCOPE_NOTE}"
    )
    return DiagnosisReport(
        **common, outcome="fix_failed", improved_code=state.get("improved_code"),
        changes=changes, validation=validation, overall_summary=summary,
    )


def report(state: AnalysisState) -> dict[str, Any]:
    return {"report": build_report(state).model_dump()}


# ── Graph ───────────────────────────────────────────────────


def build_graph() -> StateGraph:
    g = StateGraph(AnalysisState)
    for name in ("parse_input", "analyze", "map_rules", "retrieve", "diagnose", "decide",
                 "generate_fix", "revalidate"):
        g.add_node(name, getattr(nodes, name))
    g.add_node("report", report)

    g.add_edge(START, "parse_input")
    g.add_conditional_edges("parse_input", partial(nodes.route_after, next_node="analyze"), ["analyze", "report"])
    g.add_conditional_edges("analyze", partial(nodes.route_after, next_node="map_rules"), ["map_rules", "report"])
    g.add_edge("map_rules", "retrieve")
    g.add_edge("retrieve", "diagnose")
    g.add_conditional_edges("diagnose", partial(nodes.route_after, next_node="decide"), ["decide", "report"])
    g.add_conditional_edges("decide", nodes.route_after_decide, ["generate_fix", "report"])
    g.add_conditional_edges("generate_fix", partial(nodes.route_after, next_node="revalidate"), ["revalidate", "report"])
    g.add_conditional_edges("revalidate", nodes.route_after_revalidate, ["generate_fix", "report"])
    g.add_edge("report", END)
    return g


@lru_cache(maxsize=1)
def compiled_graph():
    return build_graph().compile()


def run_analysis(
    raw_input: str = "",
    file_code: str | None = None,
    project_id: str | None = None,
    level: TargetLevel | None = None,
    trace_id: str | None = None,
) -> tuple[DiagnosisReport, AnalysisState]:
    """Run the whole workflow. Returns the report and the final state (for tracing)."""
    initial: AnalysisState = {
        "raw_input": raw_input,
        "file_code": file_code,
        "project_id": project_id,
        "level_override": level,
        "trace_id": trace_id or uuid.uuid4().hex,
        "retry_count": 0,
        "warnings": [],
        "errors": [],
    }
    final = compiled_graph().invoke(initial, config={"recursion_limit": settings.recursion_limit})
    return DiagnosisReport.model_validate(final["report"]), final
