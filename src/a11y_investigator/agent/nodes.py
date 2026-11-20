"""Graph nodes (SPEC_MVP.md 4.2). Each node takes the state and returns a partial update.

External calls go through module-level names (`analyze_code`, `retrieve_docs`,
`run_diagnosis`, `run_fix`, `ensure_policies`) so tests can replace them.
"""
from __future__ import annotations

from typing import Any

from a11y_investigator.agent.decision import Decision, decide as decide_findings
from a11y_investigator.agent.state import AnalysisState
from a11y_investigator.chains.diagnosis import diagnose as run_diagnosis
from a11y_investigator.chains.improvement import RetryFeedback, generate_fix as run_fix
from a11y_investigator.config import settings
from a11y_investigator.rag.ingest import ensure_project_policies_current as ensure_policies
from a11y_investigator.rag.retriever import RetrievalResult, RetrievedDoc, retrieve as retrieve_docs
from a11y_investigator.schemas.analyzer import AnalyzerResult, TargetLevel
from a11y_investigator.schemas.diagnosis import DiagnosisOutput, FixOutput, ValidationResult
from a11y_investigator.tools.code_validation import can_retry, feedback_from, validate_generated_code
from a11y_investigator.tools.input_parser import parse_input as parse_raw_input
from a11y_investigator.tools.policy_lookup import PolicyError, load_project
from a11y_investigator.tools.rule_mapping import apply_mapping
from a11y_investigator.tools.static_analysis import StaticAnalysisError, analyze_code


def _fail(stage: str, code: str, message: str) -> dict[str, Any]:
    return {"failure": {"stage": stage, "code": code, "message": message}, "errors": [f"{stage}: {message}"]}


def resolve_target_level(
    override: TargetLevel | None, requested: TargetLevel | None, project_level: TargetLevel | None
) -> TargetLevel:
    """CLI --level > level named in the request > project.yaml target_level > AA."""
    return override or requested or project_level or settings.default_target_level  # type: ignore[return-value]


def _analysis(state: AnalysisState) -> AnalyzerResult:
    return AnalyzerResult.model_validate(state["static_result"])


def _retrieval(state: AnalysisState) -> RetrievalResult:
    return RetrievalResult(
        official=[RetrievedDoc.model_validate(d) for d in state.get("official_documents", [])],
        policies=[RetrievedDoc.model_validate(d) for d in state.get("policy_documents", [])],
    )


def _decision(state: AnalysisState) -> Decision:
    return Decision.model_validate(state["decision"])


# ── Nodes ───────────────────────────────────────────────────


def parse_input(state: AnalysisState) -> dict[str, Any]:
    project_id = state.get("project_id")
    project = None
    if project_id:
        try:
            project = load_project(project_id)
        except PolicyError as e:
            return _fail("parse_input", "unknown_project", str(e))

    parsed = parse_raw_input(state.get("raw_input", ""), state.get("file_code"))
    level = resolve_target_level(
        state.get("level_override"), parsed.requested_level, project.target_level if project else None
    )
    update: dict[str, Any] = {
        "user_request": parsed.user_request,
        "requested_level": parsed.requested_level,
        "target_level": level,
        "component_mapping": project.component_mapping if project else {},
    }
    if not parsed.ok:
        return {**update, **_fail("parse_input", parsed.error_code or "invalid_input", parsed.error_message or "")}
    return {
        **update,
        "input_code": parsed.code,
        "code_type": parsed.code_type,
        "component_hint": parsed.component_hint,
    }


def analyze(state: AnalysisState) -> dict[str, Any]:
    try:
        result = analyze_code(state["input_code"], state["code_type"], state.get("component_mapping") or None)
    except StaticAnalysisError as e:
        return _fail("analyze", e.kind, e.message)
    return {"static_result": result.model_dump()}


def map_rules(state: AnalysisState) -> dict[str, Any]:
    return {"static_result": apply_mapping(_analysis(state)).model_dump()}


def retrieve(state: AnalysisState) -> dict[str, Any]:
    project_id = state.get("project_id")
    reindexed = False
    if project_id:
        reindexed = ensure_policies(project_id)
    result = retrieve_docs(_analysis(state), state.get("component_hint"), project_id)
    return {
        "official_documents": [d.model_dump() for d in result.official],
        "policy_documents": [d.model_dump() for d in result.policies],
        "retrieval_queries": result.queries,
        "policies_reindexed": reindexed,
    }


def diagnose(state: AnalysisState) -> dict[str, Any]:
    try:
        output = run_diagnosis(
            state["input_code"], state["code_type"], _analysis(state), _retrieval(state),
            state.get("target_level", "AA"), state.get("user_request", ""),
        )
    except Exception as e:  # Bedrock throttling, validation of structured output, ...
        return _fail("diagnose", type(e).__name__, str(e)[:500])
    return {"diagnosis": output.model_dump()}


def decide(state: AnalysisState) -> dict[str, Any]:
    decision = decide_findings(
        DiagnosisOutput.model_validate(state["diagnosis"]), _analysis(state), _retrieval(state)
    )
    return {
        "decision": decision.model_dump(),
        "needs_improvement": decision.needs_improvement,
        "warnings": decision.warnings,
    }


def generate_fix(state: AnalysisState) -> dict[str, Any]:
    feedback: RetryFeedback | None = None
    previous = state.get("revalidation_result")
    if previous and previous.get("status") == "failed" and state.get("improved_code"):
        feedback = feedback_from(
            ValidationResult.model_validate(previous),
            state["improved_code"],
            AnalyzerResult.model_validate(state["after_static_result"]),
        )
    try:
        fix: FixOutput = run_fix(
            state["input_code"], state["code_type"], _decision(state), _retrieval(state),
            state.get("component_mapping") or None, state.get("target_level", "AA"), feedback,
        )
    except Exception as e:
        return _fail("generate_fix", type(e).__name__, str(e)[:500])
    return {"improved_code": fix.improved_code, "fix_changes": [c.model_dump() for c in fix.changes]}


def revalidate(state: AnalysisState) -> dict[str, Any]:
    attempt = state.get("retry_count", 0) + 1
    validation, after = validate_generated_code(
        state["input_code"], state["improved_code"] or "", state["code_type"], _analysis(state),
        _decision(state).fix_targets, state.get("component_mapping") or None,
        attempt=attempt, analyzer=analyze_code,
    )
    return {
        "revalidation_result": validation.model_dump(),
        "after_static_result": after.model_dump(),
        "retry_count": attempt if validation.status == "failed" else state.get("retry_count", 0),
    }


# ── Routing ─────────────────────────────────────────────────


def route_after(state: AnalysisState, next_node: str) -> str:
    return "report" if state.get("failure") else next_node


def route_after_decide(state: AnalysisState) -> str:
    return "generate_fix" if state.get("needs_improvement") else "report"


def route_after_revalidate(state: AnalysisState) -> str:
    validation = ValidationResult.model_validate(state["revalidation_result"])
    return "generate_fix" if can_retry(validation) else "report"
