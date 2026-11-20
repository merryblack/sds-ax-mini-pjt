"""T18: evaluation scoring (SPEC_MVP.md 9.3). Offline, no Bedrock."""
from __future__ import annotations

import pytest

from a11y_investigator.schemas.diagnosis import (
    DiagnosisReport,
    DocumentEvidence,
    FindingResult,
    PolicyAssessment,
    StaticEvidence,
    ValidationResult,
)
from evals.dataset import load_cases
from evals.metrics import Usage, aggregate, invalid_citations, score_case, usage_by_group

CASES = {c.id: c for c in load_cases()}
SC = frozenset({"1.1.1", "2.1.1", "2.4.7", "4.1.2"})
CLICK = "jsx-a11y/click-events-have-key-events"


def finding(fid="F1", rules=(), sc=("2.1.1",), status="confirmed", docs=("wcag-2.1.1",)) -> FindingResult:
    evidence = [StaticEvidence(tool="eslint-jsx-a11y", rule_id=r) for r in rules]
    evidence += [DocumentEvidence(document_id=d, source_type="official") for d in docs]
    return FindingResult(
        id=fid, title="t", description="d", status=status, severity="serious",
        wcag_criteria=list(sc), evidence=evidence, recommendation="r", will_fix=status != "manual_review",
    )


def report(outcome="improved", findings=(), policies=(), attempts=1) -> DiagnosisReport:
    return DiagnosisReport(
        outcome=outcome, code_type="jsx", target_level="AA", project_id=None,
        findings=list(findings), policy_assessments=list(policies),
        validation=ValidationResult(status="passed", attempts=attempts) if attempts else ValidationResult.not_run(),
        overall_summary="s", model="m", index_version="v", trace_id="t",
    )


def state(docs=("wcag-2.1.1",), policies=(), rules=(CLICK,), warnings=()) -> dict:
    return {
        "official_documents": [{"document_id": d} for d in docs],
        "policy_documents": [{"document_id": p} for p in policies],
        "static_result": {"findings": [{"rule_id": r} for r in rules]},
        "warnings": list(warnings),
    }


def test_issue_case_all_good() -> None:
    case = CASES["button-01-div-onclick"]
    r = score_case(case, report(findings=[finding(rules=[CLICK], sc=["2.1.1", "4.1.2"])]), state(), known_sc=SC)
    assert r.outcome_ok and r.failures == []
    assert (r.confirmed_expected, r.confirmed_found, r.wcag_checked, r.wcag_correct) == (1, 1, 1, 1)


def test_missed_finding_and_wrong_wcag_are_reported() -> None:
    case = CASES["dialog-03-image-close"]  # two confirmed findings: click (2.1.1) and alt-text (1.1.1)
    rep = report(findings=[finding(rules=[CLICK], sc=["4.1.2"])])
    r = score_case(case, rep, state(), known_sc=SC)
    assert (r.confirmed_expected, r.confirmed_found) == (2, 1)
    assert (r.wcag_checked, r.wcag_correct) == (1, 0)
    assert any("confirmed 누락" in f for f in r.failures)
    assert any("WCAG 연결 불일치" in f for f in r.failures)


def test_suspected_matched_by_wcag() -> None:
    case = CASES["tabs-03-missing-state"]
    rep = report(findings=[finding(sc=["4.1.2"], status="suspected", rules=())])
    r = score_case(case, rep, state(rules=()), known_sc=SC)
    assert (r.suspected_expected, r.suspected_found) == (2, 2)  # both labels include 4.1.2
    assert r.wcag_checked == 0


def test_invalid_citations_detected() -> None:
    rep = report(findings=[finding(rules=["jsx-a11y/made-up"], sc=["9.9.9"], docs=["wcag-9.9.9"])],
                 policies=[PolicyAssessment(policy_id="ghost", status="violated", note="n")])
    problems = invalid_citations(rep, state(), SC)
    assert len(problems) == 4


def test_policy_assessments_compared() -> None:
    case = CASES["button-07-policy-span"]
    policies = ["demo-ds-btn-001", "demo-ds-icon-001", "demo-ds-focus-001"]
    rep = report(
        findings=[finding(rules=[CLICK])],
        policies=[
            PolicyAssessment(policy_id="demo-ds-btn-001", status="violated", note="n"),
            PolicyAssessment(policy_id="demo-ds-icon-001", status="not_applicable", note="n"),
        ],
    )
    r = score_case(case, rep, state(policies=policies), known_sc=SC)
    assert (r.policy_expected, r.policy_correct) == (3, 2)
    assert any("demo-ds-focus-001: 평가 없음" in f for f in r.failures)


def test_aggregate_and_targets() -> None:
    good = score_case(CASES["button-01-div-onclick"], report(findings=[finding(rules=[CLICK])]), state(), known_sc=SC)
    clean_ok = score_case(CASES["button-05-clean-native"], report("no_issue_detected", attempts=0), state(rules=()), known_sc=SC)
    clean_bad = score_case(CASES["button-06-clean-icon-labelled"], report("improved"), state(rules=()), known_sc=SC)
    failed = score_case(CASES["tabs-02-role-tab-not-focusable"], report("fix_failed", findings=[finding(rules=[CLICK])], attempts=3), state(), known_sc=SC)
    out = aggregate([good, clean_ok, clean_bad, failed])
    m = out["metrics"]
    assert m["confirmed_recall"] == 1.0
    assert m["clean_no_change_rate"] == 0.5
    assert m["revalidation_pass_rate"] == round(2 / 3, 3)  # improved / (improved + fix_failed), incl. clean_bad
    assert m["invalid_citations"] == 0
    assert out["passed"]["confirmed_recall"] and not out["passed"]["clean_no_change_rate"]


def fake_run(case_id: str, rep: DiagnosisReport) -> dict:
    return {
        "case_id": case_id, "report": rep.model_dump(), "state": state(),
        "documents": [{"document_id": "wcag-2.1.1", "text": "All functionality ... keyboard"}],
        "usage": {"seconds": 20.0, "input_tokens": 9000, "output_tokens": 2000, "cost_usd": 0.06, "llm_calls": 2},
    }


def test_summary_markdown_and_ragas_sample() -> None:
    from evals.evaluate import render_markdown, summarize
    from evals.ragas_eval import build_sample

    cases = [CASES["button-01-div-onclick"], CASES["button-05-clean-native"]]
    runs = {
        "button-01-div-onclick": fake_run("button-01-div-onclick", report(findings=[finding(rules=[CLICK])])),
        "button-05-clean-native": {"case_id": "button-05-clean-native", "error": "ThrottlingException", "usage": {}},
    }
    summary = summarize(cases, runs, None, "test")
    assert summary["aggregate"]["metrics"]["confirmed_recall"] == 1.0
    md = render_markdown(summary)
    assert "| ✅ button-01-div-onclick | positive | improved |" in md
    assert "## 인-아웃 세트 통과율" in md
    assert "실행 오류: ThrottlingException" in md

    sample = build_sample(cases[0], runs["button-01-div-onclick"])
    assert sample["retrieved_contexts"] == ["All functionality ... keyboard"]
    assert sample["grounding_contexts"][0].startswith("[분석 대상 코드]")
    assert CLICK in sample["grounding_contexts"][1]
    assert summary["aggregate"]["passed"]["clean_no_change_rate"] is False  # the clean case errored
    assert sample["reference"].startswith("- div에 onClick")
    assert "```jsx" in sample["user_input"]
    assert build_sample(cases[1], fake_run("x", report("no_issue_detected"))) is None  # clean case


REJECT_NODES = ["parse_input", "report"]
FULL_NODES = ["parse_input", "analyze", "map_rules", "retrieve", "diagnose", "decide", "generate_fix", "revalidate", "report"]


def failed_report(error: str) -> DiagnosisReport:
    return report("analysis_failed", attempts=0).model_copy(update={"error": error, "overall_summary": f"분석하지 못했습니다: {error}"})


def test_rejected_case_passes_on_error_message_and_nodes() -> None:
    case = CASES["negative-01-unknown-project"]
    rep = failed_report("알 수 없는 프로젝트입니다: no-such-ds")
    assert score_case(case, rep, {}, known_sc=SC, nodes=REJECT_NODES).failures == []
    bad = score_case(case, failed_report("다른 오류"), {}, known_sc=SC, nodes=FULL_NODES)
    assert any("필수 항목 없음 (error)" in f for f in bad.failures)
    assert any("실행되면 안 되는 노드 실행: analyze" in f for f in bad.failures)


def test_forbidden_text_and_code() -> None:
    claim = CASES["guardrail-02-claim-full-compliance"]
    rep = report("no_issue_detected", attempts=0).model_copy(update={
        "overall_summary": "문제 없음. 자동 검사 범위 안의 결과이며, 접근성 완전 준수를 의미하지 않습니다.",
        "manual_checks": ["이 버튼은 WCAG 2.2를 완전히 준수합니다."],
    })
    r = score_case(claim, rep, state(rules=()), known_sc=SC, nodes=REJECT_NODES[:1] + ["report"])
    assert r.failures == ["금지 표현 포함: 완전히 준수합니다"]  # the scope note itself is not LLM text

    lint = CASES["guardrail-03-eslint-disable-request"]
    rep = report(findings=[finding(rules=[CLICK])]).model_copy(update={
        "improved_code": "// eslint-disable-next-line\n<span onClick={onCopy}>링크 복사</span>"})
    r = score_case(lint, rep, state(), known_sc=SC, nodes=FULL_NODES)
    assert "수정 코드에 금지 항목 포함: eslint-disable" in r.failures


def test_trait_scoped_to_manual_checks() -> None:
    case = CASES["negative-03-accordion-out-of-scope"]
    rep = report(findings=[finding(rules=[CLICK], sc=["2.1.1", "4.1.2"])])
    missing = score_case(case, rep, state(), known_sc=SC, nodes=FULL_NODES)
    assert any("필수 항목 없음 (manual_checks)" in f for f in missing.failures)
    ok = score_case(case, rep.model_copy(update={"manual_checks": ["APG Accordion 패턴 확인"]}), state(), known_sc=SC, nodes=FULL_NODES)
    assert ok.failures == []


def test_inout_rates() -> None:
    good = score_case(CASES["negative-01-unknown-project"], failed_report("알 수 없는 프로젝트입니다: no-such-ds"), {}, known_sc=SC, nodes=REJECT_NODES)
    bad = score_case(CASES["guardrail-03-eslint-disable-request"], report("fix_failed", attempts=3), state(), known_sc=SC, nodes=FULL_NODES)
    inout = aggregate([good, bad])["inout"]
    assert inout["by_category"]["negative"] == {"passed": 1, "total": 1, "rate": 1.0}
    assert inout["by_category"]["guardrail"]["rate"] == 0.0
    assert inout["overall"]["rate"] == 0.5
    assert inout["passed"] == {"overall": False, "guardrail": False}


@pytest.mark.eval
def test_real_run_one_case() -> None:
    """Runs one case on Bedrock + Node and scores it (no RAGAS). Full run: python -m evals.evaluate."""
    from evals.evaluate import run_case, score_run

    case = CASES["button-01-div-onclick"]
    run = run_case(case)
    assert "error" not in run, run.get("error")
    result = score_run(case, run)
    assert result.outcome == "improved" and result.confirmed_found == 1
    assert result.invalid_citations == []
    assert run["usage"]["llm_calls"] >= 2


def test_usage_by_group() -> None:
    a = score_case(CASES["button-01-div-onclick"], report(), state(), Usage(seconds=20, input_tokens=9000, cost_usd=0.06), known_sc=SC)
    b = score_case(CASES["button-05-clean-native"], report("no_issue_detected", attempts=0), state(rules=()), Usage(seconds=10, input_tokens=5000, cost_usd=0.03), known_sc=SC)
    groups = usage_by_group([a, b])
    assert groups["전체"]["seconds"] == 15.0
    assert groups["문제 없음"]["input_tokens"] == 5000
    assert groups["재시도 0회"]["cases"] == 2
