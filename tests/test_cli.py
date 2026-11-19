"""T16: CLI, Markdown report, trace, policies check (SERVICE_MVP.md 2.2, 3.1, 9.1, 6.2).

Offline: the analyzer, retriever, and LLM chains are replaced with the fakes in fakes.py.
"""
from __future__ import annotations

import json
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from typer.testing import CliRunner

from a11y_investigator.agent.trace import TokenUsageCallback, estimate_cost
from a11y_investigator.cli import app
from a11y_investigator.schemas.diagnosis import DiagnosisOutput

from fakes import NONINT, Fakes, finding  # noqa: E402
from samples import FIXED_A, SCENARIO_A  # noqa: E402

runner = CliRunner()


def write(tmp_path, name: str, code: str):
    path = tmp_path / name
    path.write_text(code, encoding="utf-8")
    return path


# ── analyze ─────────────────────────────────────────────────


def test_analyze_markdown_report_and_trace(tmp_path, monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(findings=[finding()], manual_checks=["색 대비"]), [FIXED_A], {FIXED_A: []})
    file = write(tmp_path, "SaveButton.jsx", SCENARIO_A)
    result = runner.invoke(app, ["analyze", "--file", str(file), "--trace-dir", str(tmp_path / "traces")])
    assert result.exit_code == 0, result.output
    out = result.stdout
    for heading in ("## 1. 요약", "## 2. 발견된 문제", "## 3. 근거", "## 4. 프로젝트 정책 적합성",
                    "## 5. 개선 필요 여부", "## 6. 개선 코드", "## 7. 변경 내용", "## 8. 재검증 결과",
                    "## 9. 수동 검증 필요 항목"):
        assert heading in out, heading
    assert "https://www.w3.org/TR/WCAG22/#keyboard" in out
    assert '<button type="button"' in out

    traces = list((tmp_path / "traces").glob("*.json"))
    assert len(traces) == 1
    trace = json.loads(traces[0].read_text(encoding="utf-8"))
    assert trace["outcome"] == "improved"
    assert [n["node"] for n in trace["nodes"]] == [
        "parse_input", "analyze", "map_rules", "retrieve", "diagnose", "decide",
        "generate_fix", "revalidate", "report",
    ]
    assert trace["retrieval"]["official"] == ["wcag-2.1.1"]
    assert len(trace["revalidations"]) == 1
    assert "[trace]" in result.stderr


def test_analyze_json_output(tmp_path, monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(findings=[finding()]), [FIXED_A], {FIXED_A: []})
    file = write(tmp_path, "a.jsx", SCENARIO_A)
    result = runner.invoke(app, ["analyze", "-f", str(file), "--json", "--no-trace"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["outcome"] == "improved" and data["validation"]["status"] == "passed"
    assert "[trace]" not in result.stderr


def test_analyze_stdin_with_request_and_level(monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})
    stdin = "AAA 기준으로 봐 줘\n```jsx\n" + SCENARIO_A.replace("<div onClick", "<button onClick").replace("</div>", "</button>") + "\n```"
    result = runner.invoke(app, ["analyze", "--json", "--no-trace", "--level", "a"], input=stdin)
    data = json.loads(result.stdout)
    assert data["target_level"] == "A"  # --level beats the request text
    assert data["outcome"] == "no_issue_detected"


def test_fix_failed_report_warns(tmp_path, monkeypatch) -> None:
    bads = [FIXED_A + f"\n// v{i}" for i in range(3)]
    Fakes(monkeypatch, DiagnosisOutput(findings=[finding()]), bads, {b: [NONINT] for b in bads})
    file = write(tmp_path, "a.jsx", SCENARIO_A)
    result = runner.invoke(app, ["analyze", "-f", str(file), "--no-trace"])
    assert result.exit_code == 0
    assert "검증되지 않은 코드" in result.stdout
    assert "새로 생긴 위반" in result.stdout


def test_analysis_failed_exit_code(tmp_path, monkeypatch) -> None:
    Fakes(monkeypatch, DiagnosisOutput(), [], {})
    file = write(tmp_path, "a.html", "<!DOCTYPE html><html><body><div onclick='x()'>x</div></body></html>")
    result = runner.invoke(app, ["analyze", "-f", str(file), "--no-trace"])
    assert result.exit_code == 1
    assert "분석 실패" in result.stdout and "React" in result.stdout


def test_bad_arguments(tmp_path) -> None:
    assert runner.invoke(app, ["analyze", "-f", str(tmp_path / "missing.jsx")]).exit_code == 2
    file = write(tmp_path, "a.jsx", SCENARIO_A)
    assert runner.invoke(app, ["analyze", "-f", str(file), "--level", "AAAA"]).exit_code == 2


# ── policies check ──────────────────────────────────────────


def test_policies_check_demo_ok() -> None:
    result = runner.invoke(app, ["policies", "check", "demo-ds"])
    assert result.exit_code == 0, result.output
    assert "정책 5개" in result.stdout and "demo-ds-btn-001" in result.stdout


def test_policies_check_reports_all_problems(tmp_path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "project.yaml").write_text("project_id: other\n", encoding="utf-8")
    (d / "a.md").write_text("---\npolicy_id: x\nproject_id: bad\ntitle: t\napplies_to: [carousel]\n---\nbody", encoding="utf-8")
    (d / "b.md").write_text("---\npolicy_id: y\nproject_id: bad\ntitle: t\nrelated_wcag: ['9.9.9']\n---\nbody", encoding="utf-8")
    (d / "c.md").write_text("---\npolicy_id: y\nproject_id: bad\ntitle: t\n---\nbody", encoding="utf-8")
    (d / "d.md").write_text("no frontmatter", encoding="utf-8")
    result = runner.invoke(app, ["policies", "check", "bad", "--policies-dir", str(tmp_path)])
    assert result.exit_code == 1
    out = result.stdout
    assert "project.yaml" in out and "a.md" in out and "9.9.9" in out and "중복" in out and "d.md" in out


def test_policies_check_missing_project(tmp_path) -> None:
    result = runner.invoke(app, ["policies", "check", "nope", "--policies-dir", str(tmp_path)])
    assert result.exit_code == 1 and "폴더가 없습니다" in result.stdout


# ── Token usage callback ────────────────────────────────────


def test_token_callback_records_node_tokens_and_cost() -> None:
    cb = TokenUsageCallback()
    run_id = uuid4()
    cb.on_chat_model_start({}, [[]], run_id=run_id, metadata={"langgraph_node": "diagnose"},
                           invocation_params={"model_id": "us.anthropic.claude-sonnet-4-6"})
    message = AIMessage(content="", usage_metadata={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200})
    cb.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)
    call = cb.calls[0]
    assert call["node"] == "diagnose" and call["input_tokens"] == 1000 and call["output_tokens"] == 200
    assert call["estimated_cost_usd"] == estimate_cost("us.anthropic.claude-sonnet-4-6", 1000, 200) > 0
    assert estimate_cost("unknown-model", 1000, 200) == 0.0
