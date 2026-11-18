"""Evidence, LLM output, and report schemas (SERVICE_MVP.md 7.2).

Three groups:
- Evidence: what a finding is based on (document or static analysis).
- LLM output: `DiagnosisOutput` (diagnosis chain) and `FixOutput` (fix chain).
  Field descriptions are sent to the model as part of the structured-output schema.
- Report: assembled by plain code. Validation results and source URLs are never
  filled by the LLM.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from a11y_investigator.schemas.analyzer import CodeType, Severity, StaticFinding, TargetLevel

FindingStatus = Literal["confirmed", "suspected", "manual_review"]
FixScope = Literal["local", "structural"]
PolicyStatus = Literal["compliant", "violated", "conflict_with_wcag", "not_applicable"]
Outcome = Literal[
    "improved", "fix_failed", "no_change_needed", "no_issue_detected", "analysis_failed"
]


# ── Evidence ────────────────────────────────────────────────


class DocumentEvidence(BaseModel):
    """A retrieved document that supports the finding."""

    kind: Literal["document"] = "document"
    document_id: str = Field(description="Must be one of the document IDs provided in the context.")
    source_type: Literal["official", "project_policy"]
    section: str | None = None


class StaticEvidence(BaseModel):
    """A static analysis result that supports the finding."""

    kind: Literal["static_analysis"] = "static_analysis"
    tool: str
    rule_id: str
    line: int | None = None


Evidence = Annotated[DocumentEvidence | StaticEvidence, Field(discriminator="kind")]


# ── LLM output ──────────────────────────────────────────────


class Finding(BaseModel):
    """One accessibility issue found in the code."""

    id: str = Field(description="Sequential ID: 'F1', 'F2', ...")
    title: str
    description: str
    status: FindingStatus = Field(
        description=(
            "confirmed: backed by static analysis or deterministically visible in code; "
            "suspected: inferred from code context; "
            "manual_review: needs rendering, runtime, or assistive-technology checks."
        )
    )
    severity: Severity
    wcag_criteria: list[str] = Field(description="WCAG success criterion numbers, e.g. ['2.1.1'].")
    location: str | None = Field(default=None, description="Line range, e.g. 'L3-L5'.")
    fix_scope: FixScope | None = Field(
        default=None,
        description=(
            "Required when status is 'suspected'. local: fix touches only this element and its "
            "handlers; structural: needs new state management or component restructuring."
        ),
    )
    evidence: list[Evidence]
    recommendation: str


class PolicyAssessment(BaseModel):
    """Compliance with one project policy, evaluated separately from WCAG."""

    policy_id: str
    status: PolicyStatus
    note: str


class DiagnosisOutput(BaseModel):
    """Structured output of the diagnosis chain."""

    findings: list[Finding] = Field(default_factory=list)
    policy_assessments: list[PolicyAssessment] = Field(default_factory=list)
    manual_checks: list[str] = Field(
        default_factory=list, description="Checks that static analysis cannot confirm."
    )


class CodeChange(BaseModel):
    """One change made in the improved code."""

    finding_ids: list[str]
    description: str


class FixOutput(BaseModel):
    """Structured output of the fix chain."""

    improved_code: str = Field(description="The complete improved code, not a diff.")
    changes: list[CodeChange] = Field(default_factory=list)


# ── Report (assembled by plain code) ────────────────────────


class ValidationResult(BaseModel):
    """Outcome of static revalidation (SERVICE_MVP.md 5.3)."""

    status: Literal["passed", "failed", "not_run"]
    attempts: int = Field(ge=0, le=3, description="0 when not run; otherwise 1-3.")
    findings_before: int = 0
    findings_after: int = 0
    new_findings: list[StaticFinding] = Field(default_factory=list)
    remaining_rule_ids: list[str] = Field(default_factory=list)
    blocked_patterns: list[str] = Field(default_factory=list)
    changed_lines: int = 0

    @classmethod
    def not_run(cls) -> ValidationResult:
        return cls(status="not_run", attempts=0)


class FindingResult(Finding):
    """A finding after the decide node."""

    will_fix: bool


class DiagnosisReport(BaseModel):
    """Final report returned by the CLI (`--json`)."""

    outcome: Outcome
    code_type: CodeType | None
    target_level: TargetLevel
    project_id: str | None
    findings: list[FindingResult] = Field(default_factory=list)
    policy_assessments: list[PolicyAssessment] = Field(default_factory=list)
    improved_code: str | None = None
    changes: list[CodeChange] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult.not_run)
    manual_checks: list[str] = Field(default_factory=list)
    sources: dict[str, str] = Field(
        default_factory=dict, description="document_id -> source_url, filled from metadata."
    )
    overall_summary: str
    error: str | None = None
    # Reproducibility
    model: str
    index_version: str
    analyzer_versions: dict[str, str] = Field(default_factory=dict)
    trace_id: str
