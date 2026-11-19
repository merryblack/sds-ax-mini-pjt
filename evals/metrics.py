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
from evals.dataset import EvalCase, ExpectedFinding

GUARDRAIL_MARKERS = ("제공되지 않은 문서 인용 제거", "인덱스에 없는 WCAG 기준 제거", "정적 분석에 없는 규칙 근거 제거")

# SERVICE_MVP.md 9.3: metric -> (target, higher_is_better)
TARGETS: dict[str, tuple[float, bool]] = {
    "confirmed_recall": (0.90, True),
    "clean_no_change_rate": (0.80, True),
    "revalidation_pass_rate": (0.80, True),
    "invalid_citations": (0, False),
    "wcag_mapping_accuracy": (0.80, True),
}


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
    code_type: str
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
    allowed_docs = {d["document_id"] for d in state.get("official_documents", [])}
    allowed_docs |= {d["document_id"] for d in state.get("policy_documents", [])}
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


def score_case(
    case: EvalCase,
    report: DiagnosisReport,
    state: dict[str, Any],
    usage: Usage | None = None,
    known_sc: frozenset[str] | None = None,
) -> CaseResult:
    known_sc = known_sc if known_sc is not None else indexed_sc()
    exp = case.expected
    r = CaseResult(
        id=case.id, component=case.component, category=case.category, code_type=case.code_type,
        outcome=report.outcome, expected_outcomes=list(exp.outcomes),
        outcome_ok=report.outcome in exp.outcomes, attempts=report.validation.attempts,
        usage=usage or Usage(),
    )
    if not r.outcome_ok:
        r.failures.append(f"outcome {report.outcome} (기대: {', '.join(exp.outcomes)})")
    if report.error:
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
    r.guardrail_removed = sum(any(m in w for m in GUARDRAIL_MARKERS) for w in state.get("warnings", []))

    actual = {pa.policy_id: pa.status for pa in report.policy_assessments}
    for pa in exp.policy_assessments:
        r.policy_expected += 1
        if actual.get(pa.policy_id) == pa.status:
            r.policy_correct += 1
        else:
            r.failures.append(f"정책 {pa.policy_id}: {actual.get(pa.policy_id, '평가 없음')} (기대: {pa.status})")
    return r


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    clean = [r for r in results if r.category == "clean"]
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
    return {"metrics": metrics, "passed": passed, "info": info}


def usage_by_group(results: list[CaseResult]) -> dict[str, dict[str, float]]:
    """Average usage per case type (for the D3 table)."""
    groups: dict[str, list[CaseResult]] = {"전체": results}
    for r in results:
        key = {"clean": "문제 없음", "policy": "정책 적용"}.get(r.category, "문제 있음")
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
