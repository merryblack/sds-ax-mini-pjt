"""Output guardrails applied in plain code (SPEC_MVP.md 8장).

T12 — citation checks on the diagnosis:
- drop document evidence whose ID was not provided to the model
- drop static evidence for rules the analyzer did not report; normalize the tool name
- drop WCAG SC numbers that are not in the indexed WCAG set
- drop policy assessments for policies that were not provided
- demote findings left without document evidence to manual_review
- forbid `confirmed` when the code could not be parsed

T14 — lint-bypass detection for generated code: a fix that silences the linter
instead of fixing the code fails revalidation.
"""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import AnalyzerResult
from a11y_investigator.schemas.diagnosis import (
    DiagnosisOutput,
    DocumentEvidence,
    Finding,
    StaticEvidence,
)

ANALYZER_TOOL = "eslint-jsx-a11y"

# Lint-bypass comments (SPEC_MVP.md 8장). Matched in // and /* */ comments.
BLOCKED_PATTERNS: dict[str, re.Pattern[str]] = {
    "eslint-disable": re.compile(r"eslint-disable(?:-next-line|-line)?\b"),
    "eslint-enable": re.compile(r"eslint-enable\b"),
    "@ts-ignore / @ts-nocheck": re.compile(r"@ts-(?:ignore|nocheck)\b"),
}


def find_blocked_patterns(original: str, improved: str) -> list[str]:
    """Bypass patterns that appear more often in `improved` than in `original`."""
    return [
        name
        for name, pattern in BLOCKED_PATTERNS.items()
        if len(pattern.findall(improved)) > len(pattern.findall(original))
    ]


@lru_cache(maxsize=1)
def indexed_sc() -> frozenset[str]:
    """WCAG SC numbers present in the index (from the generated sources manifest)."""
    manifest = yaml.safe_load((settings.manifests_dir / "sources.yaml").read_text(encoding="utf-8"))
    return frozenset(e["sc"] for e in manifest["wcag"]["success_criteria"])


def _check_finding(
    finding: Finding,
    allowed_docs: set[str],
    reported_rules: set[str],
    known_sc: frozenset[str],
    parse_ok: bool,
    warnings: list[str],
) -> Finding:
    evidence = []
    for ev in finding.evidence:
        if isinstance(ev, DocumentEvidence):
            if ev.document_id in allowed_docs:
                evidence.append(ev)
            else:
                warnings.append(f"{finding.id}: 제공되지 않은 문서 인용 제거 ({ev.document_id})")
        elif isinstance(ev, StaticEvidence):
            if ev.rule_id in reported_rules:
                evidence.append(ev.model_copy(update={"tool": ANALYZER_TOOL}))
            else:
                warnings.append(f"{finding.id}: 정적 분석에 없는 규칙 근거 제거 ({ev.rule_id})")

    criteria = [sc for sc in finding.wcag_criteria if sc in known_sc]
    for sc in set(finding.wcag_criteria) - set(criteria):
        warnings.append(f"{finding.id}: 인덱스에 없는 WCAG 기준 제거 ({sc})")

    status = finding.status
    has_doc = any(isinstance(ev, DocumentEvidence) for ev in evidence)
    if status in ("confirmed", "suspected") and not has_doc:
        warnings.append(f"{finding.id}: 근거 문서가 없어 {status} → manual_review로 강등")
        status = "manual_review"
    if status == "confirmed" and not parse_ok:
        warnings.append(f"{finding.id}: 코드 파싱 실패로 confirmed → suspected로 강등")
        status = "suspected"

    fix_scope = finding.fix_scope if status == "suspected" else None
    return finding.model_copy(
        update={"evidence": evidence, "wcag_criteria": criteria, "status": status, "fix_scope": fix_scope}
    )


def check_citations(
    diagnosis: DiagnosisOutput,
    analysis: AnalyzerResult,
    allowed_doc_ids: set[str],
    policy_ids: set[str],
    known_sc: frozenset[str] | None = None,
) -> tuple[DiagnosisOutput, list[str]]:
    """Return a cleaned copy of `diagnosis` and human-readable warnings (Korean)."""
    known_sc = known_sc if known_sc is not None else indexed_sc()
    reported_rules = {f.rule_id for f in analysis.a11y_findings}
    warnings: list[str] = []

    findings = [
        _check_finding(f, allowed_doc_ids | policy_ids, reported_rules, known_sc, analysis.parse_ok, warnings)
        for f in diagnosis.findings
    ]

    assessments = []
    for a in diagnosis.policy_assessments:
        if a.policy_id in policy_ids:
            assessments.append(a)
        else:
            warnings.append(f"제공되지 않은 정책 평가 제거 ({a.policy_id})")

    covered = {
        ev.rule_id for f in findings for ev in f.evidence if isinstance(ev, StaticEvidence)
    }
    for rule in sorted(reported_rules - covered):
        warnings.append(f"정적 분석 결과가 진단에 반영되지 않음 ({rule})")

    cleaned = diagnosis.model_copy(update={"findings": findings, "policy_assessments": assessments})
    return cleaned, warnings
