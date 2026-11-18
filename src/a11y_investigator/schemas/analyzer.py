"""Static analysis result schemas (SERVICE_MVP.md 7.2).

Produced by analyzer-js (Node) and parsed on the Python side. `wcag_refs` is
filled afterwards by the rule–WCAG mapping (T07).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CodeType = Literal["jsx", "tsx"]
TargetLevel = Literal["A", "AA", "AAA"]
Severity = Literal["critical", "serious", "moderate", "minor"]


class StaticFinding(BaseModel):
    """One rule violation reported by the static analyzer."""

    tool: Literal["eslint-jsx-a11y"]
    rule_id: str = Field(description="e.g. 'jsx-a11y/click-events-have-key-events'")
    message: str
    line: int | None = None
    column: int | None = None
    element: str | None = Field(default=None, description="e.g. 'div', 'Button'")
    wcag_refs: list[str] = Field(default_factory=list, description="e.g. ['2.1.1']")


class AnalyzerResult(BaseModel):
    """Full output of one analyzer run."""

    parse_ok: bool
    parse_error: str | None = None
    findings: list[StaticFinding] = Field(default_factory=list)
    analyzer_versions: dict[str, str] = Field(default_factory=dict)
