"""Evaluation dataset (in-out set) schema and loader (SERVICE_MVP.md 9.2, TASKS.md T20).

One YAML file per case in `evals/datasets/`. Labels describe what a correct run
should produce; `evals/evaluate.py` compares them with the real report.

Two classifications per case:
- `category` (in-out set, SERVICE.md 5장): positive / negative / edge / guardrail
- `kind` (what the diagnosis should look like): issue / clean / policy / rejected
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from a11y_investigator.schemas.analyzer import CodeType
from a11y_investigator.schemas.diagnosis import FindingStatus, FixScope, Outcome, PolicyStatus

DATASET_DIR = Path(__file__).parent / "datasets"

Component = Literal["button", "dialog", "tabs", "combobox", "other"]
Category = Literal["positive", "negative", "edge", "guardrail"]
Kind = Literal["issue", "clean", "policy", "rejected"]
Node = Literal[
    "parse_input", "analyze", "map_rules", "retrieve", "diagnose", "decide",
    "generate_fix", "revalidate", "report",
]
TRAIT_FIELDS = ("report", "summary", "findings", "manual_checks", "improved_code", "error")


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
    status: list[PolicyStatus] = Field(min_length=1, description="Acceptable statuses (a single value is allowed).")

    @field_validator("status", mode="before")
    @classmethod
    def _one_or_many(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


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
        description="Official documents a correct diagnosis should cite (required for issue / policy).",
    )
    policy_assessments: list[ExpectedPolicy] = Field(default_factory=list)
    # In-out set checks (T20)
    traits: list[str] = Field(
        default_factory=list,
        description=(
            "Must appear in the report. Format '[field:] alt1 | alt2' (any alternative, case-insensitive). "
            f"field: one of {TRAIT_FIELDS}; default 'report' = the rendered Markdown report."
        ),
    )
    forbidden: list[str] = Field(
        default_factory=list,
        description="Must NOT appear in LLM-written text (findings, recommendations, manual checks, policy notes, changes).",
    )
    forbidden_in_code: list[str] = Field(default_factory=list, description="Must NOT appear in improved_code.")
    nodes: list[Node] = Field(default_factory=list, description="Graph nodes that must run (from the trace).")
    forbidden_nodes: list[Node] = Field(default_factory=list, description="Graph nodes that must NOT run.")


def parse_trait(trait: str) -> tuple[str, list[str]]:
    """'manual_checks: 아코디언 | Accordion' -> ('manual_checks', ['아코디언', 'Accordion'])."""
    field, sep, rest = trait.partition(":")
    if sep and field.strip() in TRAIT_FIELDS:
        target, text = field.strip(), rest
    else:
        target, text = "report", trait
    return target, [alt.strip() for alt in text.split("|") if alt.strip()]


class EvalCase(BaseModel):
    id: str
    category: Category
    kind: Kind
    component: Component
    code_type: CodeType | None = None
    request: str
    project_id: str | None = None
    code: str | None = None
    raw_input: str | None = Field(
        default=None,
        description="Passed as-is instead of request + file code (e.g. several fences, HTML in a fence).",
    )
    note: str | None = None
    expected: Expected

    @field_validator("code")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.rstrip("\n") if value else value

    @property
    def run_inputs(self) -> tuple[str, str | None]:
        """(raw_input, file_code) for run_analysis."""
        if self.raw_input is not None:
            return self.raw_input, None
        return self.request, self.code

    @model_validator(mode="after")
    def _kind_rules(self) -> EvalCase:
        exp = self.expected
        if (self.code is None) == (self.raw_input is None):
            raise ValueError("set exactly one of code / raw_input")
        if self.kind == "rejected":
            if exp.outcomes != ["analysis_failed"] or exp.findings or exp.static_rule_ids:
                raise ValueError("rejected cases expect only analysis_failed, with no findings or static rules")
            return self
        if self.code is None or self.code_type is None:
            raise ValueError("analyzed cases need code and code_type")
        if self.kind == "clean":
            if exp.static_rule_ids or any(f.status == "confirmed" for f in exp.findings):
                raise ValueError("clean cases must have no static rules and no confirmed findings")
            if not set(exp.outcomes) <= {"no_issue_detected", "no_change_needed"}:
                raise ValueError("clean cases must expect a no-change outcome")
        elif not exp.findings or not exp.document_ids:
            raise ValueError(f"{self.kind} cases need expected findings and document_ids")
        if self.kind == "policy" and not (self.project_id and exp.policy_assessments):
            raise ValueError("policy cases need project_id and expected policy_assessments")
        if self.kind != "policy" and self.project_id:
            raise ValueError("only policy (or rejected) cases set project_id")
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
