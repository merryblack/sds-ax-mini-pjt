"""The `decide` step: guardrails + fix decision, in plain code (SPEC_MVP.md 5.2).

| status        | will_fix                                  |
|---------------|-------------------------------------------|
| confirmed     | True                                      |
| suspected     | True only when fix_scope == "local"       |
| manual_review | False                                     |

When the code could not be parsed nothing is fixed (SPEC_MVP.md 5.1).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from a11y_investigator.middleware.safety import check_citations
from a11y_investigator.rag.retriever import RetrievalResult
from a11y_investigator.schemas.analyzer import AnalyzerResult
from a11y_investigator.schemas.diagnosis import (
    DiagnosisOutput,
    Finding,
    FindingResult,
    PolicyAssessment,
)


class Decision(BaseModel):
    findings: list[FindingResult] = Field(default_factory=list)
    policy_assessments: list[PolicyAssessment] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    needs_improvement: bool = False
    warnings: list[str] = Field(default_factory=list)

    @property
    def fix_targets(self) -> list[FindingResult]:
        return [f for f in self.findings if f.will_fix]


def will_fix(finding: Finding, parse_ok: bool = True) -> bool:
    if not parse_ok:
        return False
    if finding.status == "confirmed":
        return True
    if finding.status == "suspected":
        return finding.fix_scope == "local"  # missing scope counts as structural
    return False


def decide(
    diagnosis: DiagnosisOutput,
    analysis: AnalyzerResult,
    retrieval: RetrievalResult,
    known_sc: frozenset[str] | None = None,
) -> Decision:
    cleaned, warnings = check_citations(
        diagnosis,
        analysis,
        allowed_doc_ids={d.document_id for d in retrieval.official},
        policy_ids={d.document_id for d in retrieval.policies},
        known_sc=known_sc,
    )
    findings = [
        FindingResult.model_validate({**f.model_dump(), "will_fix": will_fix(f, analysis.parse_ok)})
        for f in cleaned.findings
    ]
    return Decision(
        findings=findings,
        policy_assessments=cleaned.policy_assessments,
        manual_checks=cleaned.manual_checks,
        needs_improvement=any(f.will_fix for f in findings),
        warnings=warnings,
    )
