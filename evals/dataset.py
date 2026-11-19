"""Evaluation dataset schema and loader (SERVICE_MVP.md 9.2).

One YAML file per case in `evals/datasets/`. Labels describe what a correct run
should produce; `evals/evaluate.py` (T18) compares them with the real report.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from a11y_investigator.schemas.analyzer import CodeType
from a11y_investigator.schemas.diagnosis import FindingStatus, FixScope, Outcome, PolicyStatus

DATASET_DIR = Path(__file__).parent / "datasets"

Component = Literal["button", "dialog", "tabs", "combobox"]
Category = Literal["issue", "clean", "policy"]


class ExpectedFinding(BaseModel):
    """One issue a correct diagnosis must report."""

    description: str = Field(description="Reference answer in Korean; also the RAGAS `reference`.")
    status: FindingStatus
    wcag_criteria: list[str] = Field(min_length=1)
    rule_ids: list[str] = Field(
        default_factory=list,
        description="Analyzer rules that back this finding (any one matches). Empty = no static rule.",
    )
    fix_scope: FixScope | None = None

    @model_validator(mode="after")
    def _scope_for_suspected(self) -> ExpectedFinding:
        if self.status == "suspected" and self.fix_scope is None:
            raise ValueError("suspected findings need fix_scope (decide rule, SERVICE_MVP.md 5.2)")
        return self


class ExpectedPolicy(BaseModel):
    policy_id: str
    status: PolicyStatus


class Expected(BaseModel):
    outcomes: list[Outcome] = Field(
        min_length=1, description="Acceptable outcomes; clean code may end in either no-change outcome."
    )
    static_rule_ids: list[str] = Field(
        default_factory=list, description="Exact set of rules the analyzer reports on the input code."
    )
    findings: list[ExpectedFinding] = Field(default_factory=list)
    document_ids: list[str] = Field(
        default_factory=list,
        description="Official documents a correct diagnosis should cite (required unless clean).",
    )
    policy_assessments: list[ExpectedPolicy] = Field(default_factory=list)


class EvalCase(BaseModel):
    id: str
    component: Component
    category: Category
    code_type: CodeType
    request: str
    project_id: str | None = None
    code: str
    expected: Expected

    @field_validator("code")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.rstrip("\n")

    @model_validator(mode="after")
    def _category_rules(self) -> EvalCase:
        exp = self.expected
        if self.category == "clean":
            if exp.static_rule_ids or any(f.status == "confirmed" for f in exp.findings):
                raise ValueError("clean cases must have no static rules and no confirmed findings")
            if not set(exp.outcomes) <= {"no_issue_detected", "no_change_needed"}:
                raise ValueError("clean cases must expect a no-change outcome")
        else:
            if not exp.findings or not exp.document_ids:
                raise ValueError(f"{self.category} cases need expected findings and document_ids")
        if (self.category == "policy") != bool(self.project_id):
            raise ValueError("policy cases (and only those) set project_id")
        if self.category == "policy" and not exp.policy_assessments:
            raise ValueError("policy cases need expected policy_assessments")
        for f in exp.findings:
            unknown = set(f.rule_ids) - set(exp.static_rule_ids)
            if unknown:
                raise ValueError(f"finding rule_ids not in static_rule_ids: {sorted(unknown)}")
        covered = {r for f in exp.findings for r in f.rule_ids}
        if set(exp.static_rule_ids) - covered:
            raise ValueError(f"static rules without a finding: {sorted(set(exp.static_rule_ids) - covered)}")
        return self


def load_case(path: Path) -> EvalCase:
    case = EvalCase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if case.id != path.stem:
        raise ValueError(f"{path.name}: id {case.id!r} must match the file name")
    return case


def load_cases(directory: Path = DATASET_DIR) -> list[EvalCase]:
    return [load_case(p) for p in sorted(directory.glob("*.yaml"))]
