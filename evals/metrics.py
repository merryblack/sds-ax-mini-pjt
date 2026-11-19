"""Scoring one run against its labels, and the 9.3 metrics over all cases.

Pure functions (no Bedrock, no Node) so they can be unit-tested offline.

Matching rules
- An expected finding with `rule_ids` matches a reported finding that cites one of
  those rules as static evidence.
- An expected finding without `rule_ids` matches a reported finding that shares
  at least one WCAG criterion.
- WCAG mapping accuracy is measured only on rule-backed matches: the matched
  finding must share a criterion with the label.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from a11y_investigator.middleware.safety import indexed_sc
from a11y_investigator.schemas.diagnosis import (
    DiagnosisReport,
    DocumentEvidence,
    FindingResult,
    StaticEvidence,
)
from a11y_investigator.report_markdown import render_markdown as render_report
from evals.dataset import EvalCase, ExpectedFinding, parse_trait

GUARDRAIL_MARKERS = ("제공되지 않은 문서 인용 제거", "인덱스에 없는 WCAG 기준 제거", "정적 분석에 없는 규칙 근거 제거")

# SERVICE_MVP.md 9.3: metric -> (target, higher_is_better)
TARGETS: dict[str, tuple[float, bool]] = {
    "confirmed_recall": (0.90, True),
    "clean_no_change_rate": (0.80, True),
    "revalidation_pass_rate": (0.80, True),
    "invalid_citations": (0, False),
    "wcag_mapping_accuracy": (0.80, True),
}


# SERVICE.md 5장: in-out set pass rate overall and for guardrail cases
INOUT_TARGETS = {"overall": 0.80, "guardrail": 1.00}
CATEGORIES = ("positive", "negative", "edge", "guardrail")


class Usage(BaseModel):
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0


class CaseResult(BaseModel):
    id: str
    component: str
    category: str
    kind: str
    code_type: str | None
    outcome: str
    expected_outcomes: list[str]
    outcome_ok: bool
    attempts: int = 0
    confirmed_expected: int = 0
    confirmed_found: int = 0
    suspected_expected: int = 0
    suspected_found: int = 0
    wcag_checked: int = 0
    wcag_correct: int = 0
    invalid_citations: list[str] = Field(default_factory=list)
    guardrail_removed: int = 0
    policy_expected: int = 0
    policy_correct: int = 0
    failures: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


def _rules_of(f: FindingResult) -> set[str]:
    return {ev.rule_id for ev in f.evidence if isinstance(ev, StaticEvidence)}


def match(expected: ExpectedFinding, reported: list[FindingResult]) -> list[FindingResult]:
    if expected.rule_ids:
        return [f for f in reported if _rules_of(f) & set(expected.rule_ids)]
    return [f for f in reported if set(f.wcag_criteria) & set(expected.wcag_criteria)]


def invalid_citations(report: DiagnosisReport, state: dict[str, Any], known_sc: frozenset[str]) -> list[str]:
    """Citations in the final report that point at nothing real (target: 0)."""
    allowed_docs = {d["document_id"] for d in state.get("official_documents") or []}
    allowed_docs |= {d["document_id"] for d in state.get("policy_documents") or []}
    reported_rules = {f["rule_id"] for f in (state.get("static_result") or {}).get("findings", [])}
    problems = []
    for f in report.findings:
        for ev in f.evidence:
            if isinstance(ev, DocumentEvidence) and ev.document_id not in allowed_docs:
                problems.append(f"{f.id}: 문서 {ev.document_id}")
            if isinstance(ev, StaticEvidence) and ev.rule_id not in reported_rules:
                problems.append(f"{f.id}: 규칙 {ev.rule_id}")
        problems += [f"{f.id}: SC {sc}" for sc in f.wcag_criteria if sc not in known_sc]
    for pa in report.policy_assessments:
        if pa.policy_id not in allowed_docs:
            problems.append(f"정책 {pa.policy_id}")
    return problems


def report_texts(report: DiagnosisReport) -> dict[str, str]:
    """Texts the trait / forbidden checks look at."""
    nl = "\n"
    findings = nl.join(f"{f.title}{nl}{f.description}{nl}{f.recommendation}" for f in report.findings)
    llm_text = nl.join([
        findings,
        nl.join(report.manual_checks),
        nl.join(pa.note for pa in report.policy_assessments),
        nl.join(c.description for c in report.changes),
    ])
    return {
        "report": render_report(report),
        "summary": report.overall_summary,
        "findings": findings,
        "manual_checks": nl.join(report.manual_checks),
        "improved_code": report.improved_code or "",
        "error": report.error or "",
        "llm_text": llm_text,
    }


def check_inout(case: EvalCase, report: DiagnosisReport, nodes: list[str] | None) -> list[str]:
    """In-out set checks (T20): required traits, forbidden text, graph nodes."""
    exp = case.expected
    texts = report_texts(report)
    failures = []
    for trait in exp.traits:
        target, alts = parse_trait(trait)
        if not any(a.lower() in texts[target].lower() for a in alts):
            failures.append(f"필수 항목 없음 ({target}): {' | '.join(alts)}")
    for word in exp.forbidden:
        if word.lower() in texts["llm_text"].lower():
            failures.append(f"금지 표현 포함: {word}")
    for word in exp.forbidden_in_code:
        if word in texts["improved_code"]:
            failures.append(f"수정 코드에 금지 항목 포함: {word}")
    if nodes is not None:
        ran = set(nodes)
        missing = [n for n in exp.nodes if n not in ran]
        extra = [n for n in exp.forbidden_nodes if n in ran]
        if missing:
            failures.append(f"실행되지 않은 노드: {', '.join(missing)}")
        if extra:
            failures.append(f"실행되면 안 되는 노드 실행: {', '.join(extra)}")
    return failures


def score_case(
    case: EvalCase,
    report: DiagnosisReport,
    state: dict[str, Any],
    usage: Usage | None = None,
    known_sc: frozenset[str] | None = None,
    nodes: list[str] | None = None,
) -> CaseResult:
    known_sc = known_sc if known_sc is not None else indexed_sc()
    exp = case.expected
    r = CaseResult(
        id=case.id, component=case.component, category=case.category, kind=case.kind,
        code_type=case.code_type, outcome=report.outcome, expected_outcomes=list(exp.outcomes),
        outcome_ok=report.outcome in exp.outcomes, attempts=report.validation.attempts,
        usage=usage or Usage(),
    )
    if not r.outcome_ok:
        r.failures.append(f"outcome {report.outcome} (기대: {', '.join(exp.outcomes)})")
    if report.error and not r.outcome_ok:
        r.failures.append(f"error: {report.error[:200]}")

    for f in exp.findings:
        found = match(f, report.findings)
        if f.status == "confirmed":
            r.confirmed_expected += 1
            r.confirmed_found += bool(found)
            if not found:
                r.failures.append(f"confirmed 누락: {f.description[:60]}")
        else:
            r.suspected_expected += 1
            r.suspected_found += bool(found)
        if f.rule_ids and found:
            r.wcag_checked += 1
            if any(set(m.wcag_criteria) & set(f.wcag_criteria) for m in found):
                r.wcag_correct += 1
            else:
                got = sorted({sc for m in found for sc in m.wcag_criteria})
                r.failures.append(f"WCAG 연결 불일치: 기대 {f.wcag_criteria}, 결과 {got}")

    r.invalid_citations = invalid_citations(report, state, known_sc)
    if r.invalid_citations:
        r.failures.append(f"허위 인용 {len(r.invalid_citations)}건: {r.invalid_citations[:3]}")
    r.guardrail_removed = sum(any(m in w for m in GUARDRAIL_MARKERS) for w in state.get("warnings") or [])

    actual = {pa.policy_id: pa.status for pa in report.policy_assessments}
    for pa in exp.policy_assessments:
        r.policy_expected += 1
        if actual.get(pa.policy_id) in pa.status:
            r.policy_correct += 1
        else:
            r.failures.append(
                f"정책 {pa.policy_id}: {actual.get(pa.policy_id, '평가 없음')} (기대: {', '.join(pa.status)})"
            )
    r.failures += check_inout(case, report, nodes)
    return r


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    clean = [r for r in results if r.kind == "clean"]
    attempted = [r for r in results if r.outcome in ("improved", "fix_failed")]
    metrics = {
        "confirmed_recall": _ratio(sum(r.confirmed_found for r in results), sum(r.confirmed_expected for r in results)),
        "clean_no_change_rate": _ratio(sum(r.outcome_ok for r in clean), len(clean)),
        "revalidation_pass_rate": _ratio(sum(r.outcome == "improved" for r in attempted), len(attempted)),
        "invalid_citations": sum(len(r.invalid_citations) for r in results),
        "wcag_mapping_accuracy": _ratio(sum(r.wcag_correct for r in results), sum(r.wcag_checked for r in results)),
    }
    passed: dict[str, bool | None] = {}
    for name, (target, higher) in TARGETS.items():
        value = metrics[name]  # None: no case to measure (e.g. a filtered run)
        passed[name] = None if value is None else (value >= target if higher else value <= target)
    info = {
        "outcome_accuracy": _ratio(sum(r.outcome_ok for r in results), len(results)),
        "suspected_detection": _ratio(sum(r.suspected_found for r in results), sum(r.suspected_expected for r in results)),
        "policy_accuracy": _ratio(sum(r.policy_correct for r in results), sum(r.policy_expected for r in results)),
        "guardrail_removed": sum(r.guardrail_removed for r in results),
        "analysis_failed": sum(r.outcome == "analysis_failed" for r in results),
        "fix_attempted": len(attempted),
    }
    return {"metrics": metrics, "passed": passed, "info": info, "inout": inout_rates(results)}


def inout_rates(results: list[CaseResult]) -> dict[str, Any]:
    """Pass rate per in-out category (a case passes when it has no failures)."""
    by_cat = {}
    for cat in CATEGORIES:
        rs = [r for r in results if r.category == cat]
        by_cat[cat] = {"passed": sum(not r.failures for r in rs), "total": len(rs),
                       "rate": _ratio(sum(not r.failures for r in rs), len(rs))}
    overall = {"passed": sum(not r.failures for r in results), "total": len(results),
               "rate": _ratio(sum(not r.failures for r in results), len(results))}
    targets = {
        key: (None if rate is None else rate >= INOUT_TARGETS[key])
        for key, rate in (("overall", overall["rate"]), ("guardrail", by_cat["guardrail"]["rate"]))
    }
    return {"overall": overall, "by_category": by_cat, "passed": targets}


def usage_by_group(results: list[CaseResult]) -> dict[str, dict[str, float]]:
    """Average usage per case type (for the D3 table)."""
    groups: dict[str, list[CaseResult]] = {"전체": results}
    for r in results:
        key = {"clean": "문제 없음", "policy": "정책 적용", "rejected": "입력 거절"}.get(r.kind, "문제 있음")
        groups.setdefault(key, []).append(r)
        groups.setdefault(f"재시도 {max(r.attempts - 1, 0)}회", []).append(r)
    out = {}
    for key, rs in groups.items():
        n = len(rs)
        out[key] = {
            "cases": n,
            "seconds": round(sum(r.usage.seconds for r in rs) / n, 1),
            "input_tokens": round(sum(r.usage.input_tokens for r in rs) / n),
            "output_tokens": round(sum(r.usage.output_tokens for r in rs) / n),
            "cost_usd": round(sum(r.usage.cost_usd for r in rs) / n, 4),
            "llm_calls": round(sum(r.usage.llm_calls for r in rs) / n, 1),
        }
    return out
