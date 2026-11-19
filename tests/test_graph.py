"""T15: graph routing, report, level resolution, policy auto-reindex (SERVICE_MVP.md 4장, 6.2).

Offline tests replace the analyzer, retriever, and LLM chains with fakes.
`-m llm` runs the M2 milestone on the real pipeline.
"""
from __future__ import annotations

import json

import pytest

from a11y_investigator.agent import nodes
from a11y_investigator.agent.graph import UNVERIFIED_WARNING, run_analysis
from a11y_investigator.agent.nodes import resolve_target_level
from a11y_investigator.rag.ingest import (
    ensure_project_policies_current,
    load_policy_hashes,
    project_policy_hash,
)
from a11y_investigator.rag.retriever import RetrievalResult, RetrievedDoc
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.schemas.diagnosis import (
    CodeChange,
    DiagnosisOutput,
    DocumentEvidence,
    Finding,
    FixOutput,
    StaticEvidence,
)

from fakes import NONINT, Fakes, finding  # noqa: E402
from samples import FIXED_A, SCENARIO_A, SCENARIO_B, fenced  # noqa: E402


# ── Level resolution ────────────────────────────────────────


@pytest.mark.parametrize(
    ("override", "requested", "project", "expected"),
    [("A", "AAA", "AA", "A"), (None, "AAA", "A", "AAA"), (None, None, "A", "A"), (None, None, None, "AA")],
)
def test_target_level_priority(override, requested, project, expected) -> None:
    assert resolve_target_level(override, requested, project) == expected


# ── Routing with fakes ──────────────────────────────────────


def test_improved_path(monkeypatch) -> None:
    fakes = Fakes(monkeypatch, DiagnosisOutput(findings=[finding()]), [FIXED_A], {FIXED_A: []})
    report, state = run_analysis(fenced(SCENARIO_A))
    assert report.outcome == "improved"
    assert report.improved_code == FIXED_A
    assert report.validation.status == "passed" and report.validation.attempts == 1
    assert report.findings[0].will_fix
    assert report.sources == {"wcag-2.1.1": "https://www.w3.org/TR/WCAG22/#keyboard"}
    assert report.analyzer_versions == {"eslint": "9"}
    assert report.trace_id and report.model and report.index_version
    assert "완전 준수를 의미하지 않습니다" in report.overall_summary
    assert fakes.fix_calls == [None]


def test_retry_then_pass(monkeypatch) -> None:
    bad = FIXED_A + "\n// v1"
    fakes = Fakes(monkeypatch, DiagnosisOutput(findings=[finding()]), [bad, FIXED_A], {bad: [NONINT], FIXED_A: []})
    report, state = run_analysis(fenced(SCENARIO_A))
    assert report.outcome == "improved" and report.validation.attempts == 2
    assert fakes.fix_calls[0] is None
    assert fakes.fix_calls[1].new_violations and NONINT in fakes.fix_calls[1].new_violations[0]


def test_fix_failed_after_three_attempts(monkeypatch) -> None:
    bads = [FIXED_A + f"\n// v{i}" for i in range(3)]
    fakes = Fakes(monkeypatch, DiagnosisOutput(findings=[finding()]), bads, {b: [NONINT] for b in bads})
    report, _ = run_analysis(fenced(SCENARIO_A))
    assert report.outcome == "fix_failed"
    assert len(fakes.fix_calls) == 3 and report.validation.attempts == 3
    assert report.improved_code == bads[-1]
    assert report.overall_summary.startswith(UNVERIFIED_WARNING)


def test_no_issue_detected(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(manual_checks=["색 대비 확인"]), [], {})
    report, _ = run_analysis(fenced(SCENARIO_B))
    assert report.outcome == "no_issue_detected"
    assert report.improved_code is None and report.validation.status == "not_run"
    assert report.manual_checks == ["색 대비 확인"]


def test_no_change_needed_for_structural_only(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(findings=[finding("suspected", rule=None, fix_scope="structural")]), [], {})
    report, _ = run_analysis(fenced(SCENARIO_B))
    assert report.outcome == "no_change_needed"
    assert not report.findings[0].will_fix


def test_input_too_long_is_analysis_failed(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})
    code = "export function A() {\n" + "  const x = 1;\n" * 300 + "  return <div />;\n}"
    report, state = run_analysis(fenced(code))
    assert report.outcome == "analysis_failed" and "300" in (report.error or "")
    assert "static_result" not in state  # analyze never ran


def test_unknown_project_is_analysis_failed(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})
    report, _ = run_analysis(fenced(SCENARIO_A), project_id="no-such-project")
    assert report.outcome == "analysis_failed" and "no-such-project" in (report.error or "")


def test_llm_error_in_diagnosis(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})

    def boom(*a, **k):
        raise RuntimeError("ThrottlingException: Too many tokens per day")

    monkeypatch.setattr(nodes, "run_diagnosis", boom)
    report, state = run_analysis(fenced(SCENARIO_A))
    assert report.outcome == "analysis_failed" and "Throttling" in report.error
    assert state["errors"]


def test_level_override_and_project_level(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})
    report, _ = run_analysis("AAA 기준으로\n" + fenced(SCENARIO_B), level="A")
    assert report.target_level == "A"
    report, _ = run_analysis("AAA 기준으로\n" + fenced(SCENARIO_B))
    assert report.target_level == "AAA"
    report, _ = run_analysis(fenced(SCENARIO_B), project_id="demo-ds")
    assert report.target_level == "AA" and report.project_id == "demo-ds"


# ── Policy auto-reindex (hash check) ────────────────────────


def make_project(root, pid="p1", body="정책 v1"):
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.yaml").write_text(f"project_id: {pid}\n", encoding="utf-8")
    (d / "a.md").write_text(f"---\npolicy_id: {pid}-001\nproject_id: {pid}\ntitle: t\n---\n{body}\n", encoding="utf-8")
    return d


def test_policy_hash_changes_with_content(tmp_path) -> None:
    make_project(tmp_path)
    h1 = project_policy_hash("p1", tmp_path)
    assert h1 == project_policy_hash("p1", tmp_path)
    (tmp_path / "p1" / "a.md").write_text("changed", encoding="utf-8")
    assert project_policy_hash("p1", tmp_path) != h1
    (tmp_path / "p1" / "b.md").write_text("new file", encoding="utf-8")
    assert len({h1, project_policy_hash("p1", tmp_path)}) == 2


def test_ensure_reindexes_only_when_changed(tmp_path) -> None:
    make_project(tmp_path)
    hash_file = tmp_path / "hashes.json"
    calls: list[str] = []
    reindex = calls.append
    assert ensure_project_policies_current("p1", tmp_path, hash_file, reindex) is True  # first time
    assert ensure_project_policies_current("p1", tmp_path, hash_file, reindex) is False  # unchanged
    make_project(tmp_path, body="정책 v2")  # user edits the policy
    assert ensure_project_policies_current("p1", tmp_path, hash_file, reindex) is True
    assert calls == ["p1", "p1"]
    assert load_policy_hashes(hash_file)["p1"] == project_policy_hash("p1", tmp_path)
    assert json.loads(hash_file.read_text(encoding="utf-8")).keys() == {"p1"}


# ── M2 on the real pipeline ─────────────────────────────────


@pytest.mark.llm
def test_m2_scenario_a_improved() -> None:
    report, state = run_analysis(fenced(SCENARIO_A))
    assert report.outcome == "improved", (report.overall_summary, state.get("errors"))
    assert "<button" in report.improved_code
    assert report.validation.status == "passed"
    assert report.sources and all(u.startswith("https://www.w3.org/") for u in report.sources.values())


@pytest.mark.llm
def test_m2_scenario_b_unchanged() -> None:
    report, _ = run_analysis(fenced(SCENARIO_B))
    assert report.outcome in ("no_issue_detected", "no_change_needed")
    assert report.improved_code is None
