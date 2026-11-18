"""T03: schema construction, serialization, and state reducer."""
from __future__ import annotations

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import TypeAdapter, ValidationError

from a11y_investigator.agent.state import AnalysisState
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.schemas.diagnosis import (
    DiagnosisOutput,
    DiagnosisReport,
    DocumentEvidence,
    Evidence,
    Finding,
    FindingResult,
    FixOutput,
    StaticEvidence,
    ValidationResult,
)

SCENARIO_A_FINDING = StaticFinding(
    tool="eslint-jsx-a11y",
    rule_id="jsx-a11y/click-events-have-key-events",
    message="Visible, non-interactive elements with click handlers must have a key event.",
    line=3,
    column=5,
    element="div",
    wcag_refs=["2.1.1"],
)


def make_finding(**overrides) -> Finding:
    data = {
        "id": "F1",
        "title": "Clickable div is not keyboard accessible",
        "description": "A div with onClick has no keyboard handler or button semantics.",
        "status": "confirmed",
        "severity": "serious",
        "wcag_criteria": ["2.1.1", "4.1.2"],
        "location": "L3-L5",
        "evidence": [
            {"kind": "static_analysis", "tool": "eslint-jsx-a11y",
             "rule_id": "jsx-a11y/click-events-have-key-events", "line": 3},
            {"kind": "document", "document_id": "wcag-2.1.1", "source_type": "official"},
        ],
        "recommendation": "Use a native <button type=\"button\">.",
    }
    data.update(overrides)
    return Finding.model_validate(data)


# ── Analyzer ────────────────────────────────────────────────


def test_analyzer_result_roundtrip() -> None:
    result = AnalyzerResult(
        parse_ok=True,
        findings=[SCENARIO_A_FINDING],
        analyzer_versions={"eslint": "9.39.5", "eslint-plugin-jsx-a11y": "6.10.2"},
    )
    restored = AnalyzerResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_analyzer_parse_failure_defaults() -> None:
    result = AnalyzerResult(parse_ok=False, parse_error="Unexpected token (3:5)")
    assert result.findings == []
    assert result.analyzer_versions == {}


def test_static_finding_rejects_unknown_tool() -> None:
    with pytest.raises(ValidationError):
        StaticFinding(tool="html-validate", rule_id="x", message="y")


# ── Evidence discriminator ──────────────────────────────────


def test_evidence_discriminator_picks_model() -> None:
    adapter = TypeAdapter(Evidence)
    doc = adapter.validate_python(
        {"kind": "document", "document_id": "wcag-2.1.1", "source_type": "official"}
    )
    static = adapter.validate_python(
        {"kind": "static_analysis", "tool": "eslint-jsx-a11y", "rule_id": "r"}
    )
    assert isinstance(doc, DocumentEvidence)
    assert isinstance(static, StaticEvidence)


def test_evidence_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Evidence).validate_python({"kind": "guess", "document_id": "x"})


# ── LLM output ──────────────────────────────────────────────


def test_finding_parses_mixed_evidence() -> None:
    finding = make_finding()
    assert isinstance(finding.evidence[0], StaticEvidence)
    assert isinstance(finding.evidence[1], DocumentEvidence)
    assert finding.fix_scope is None


def test_finding_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        make_finding(status="probably")


def test_diagnosis_output_roundtrip() -> None:
    output = DiagnosisOutput(
        findings=[make_finding(), make_finding(id="F2", status="suspected", fix_scope="local")],
        manual_checks=["Check focus visibility in the browser."],
    )
    restored = DiagnosisOutput.model_validate_json(output.model_dump_json())
    assert restored == output
    assert restored.findings[1].fix_scope == "local"


def test_diagnosis_output_schema_is_json_schema() -> None:
    schema = DiagnosisOutput.model_json_schema()
    assert "findings" in schema["properties"]


def test_fix_output_defaults() -> None:
    assert FixOutput(improved_code="<button />").changes == []


# ── Report ──────────────────────────────────────────────────


def test_finding_result_extends_finding() -> None:
    finding = make_finding()
    result = FindingResult.model_validate({**finding.model_dump(), "will_fix": True})
    assert result.will_fix is True
    assert result.id == "F1"


def test_validation_result_not_run() -> None:
    v = ValidationResult.not_run()
    assert v.status == "not_run" and v.attempts == 0


def test_validation_attempts_bounded() -> None:
    with pytest.raises(ValidationError):
        ValidationResult(status="passed", attempts=4)


def test_report_minimal_analysis_failed() -> None:
    report = DiagnosisReport(
        outcome="analysis_failed",
        code_type=None,
        target_level="AA",
        project_id=None,
        overall_summary="입력 코드가 300줄을 초과합니다.",
        error="input_too_long",
        model="us.anthropic.claude-sonnet-4-6",
        index_version="index-v1",
        trace_id="t-1",
    )
    assert report.validation.status == "not_run"
    assert DiagnosisReport.model_validate_json(report.model_dump_json()) == report


# ── State reducer ───────────────────────────────────────────


def test_errors_reducer_appends_across_nodes() -> None:
    graph = StateGraph(AnalysisState)
    graph.add_node("a", lambda s: {"errors": ["from a"]})
    graph.add_node("b", lambda s: {"errors": ["from b"]})
    graph.add_edge(START, "a")
    graph.add_edge("a", "b")
    graph.add_edge("b", END)
    out = graph.compile().invoke({"errors": []})
    assert out["errors"] == ["from a", "from b"]
