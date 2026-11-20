"""Rule ID -> WCAG SC / APG pattern mapping (SPEC_MVP.md 6.3).

Static analysis rules carry no WCAG information, so a hand-curated YAML table
(`knowledge/manifests/rule-wcag-map.yaml`) fills `StaticFinding.wcag_refs`.
The same table drives exact document lookup and serves as the evaluation answer key.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import AnalyzerResult, Severity, StaticFinding

logger = logging.getLogger(__name__)

DEFAULT_MAP_PATH = settings.manifests_dir / "rule-wcag-map.yaml"
APG_PATTERNS = ("button", "dialog", "tabs", "combobox")
_SC_RE = re.compile(r"^[1-4]\.\d{1,2}\.\d{1,2}$")


class RuleMapping(BaseModel):
    rule_id: str
    tool: str
    wcag: list[str] = Field(default_factory=list)
    apg_pattern: str | None = None
    default_severity: Severity
    note: str | None = None

    @field_validator("wcag")
    @classmethod
    def _valid_sc(cls, values: list[str]) -> list[str]:
        bad = [v for v in values if not _SC_RE.match(v)]
        if bad:
            raise ValueError(f"invalid WCAG SC id(s): {bad}")
        return values

    @field_validator("apg_pattern")
    @classmethod
    def _valid_pattern(cls, value: str | None) -> str | None:
        if value is not None and value not in APG_PATTERNS:
            raise ValueError(f"unknown APG pattern: {value}")
        return value


RuleMap = dict[str, RuleMapping]


@lru_cache(maxsize=4)
def load_rule_map(path: Path = DEFAULT_MAP_PATH) -> RuleMap:
    """Load and validate the mapping table. Raises ValueError on duplicates or bad entries."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rule_map: RuleMap = {}
    for entry in data.get("rules", []):
        mapping = RuleMapping.model_validate(entry)
        if mapping.rule_id in rule_map:
            raise ValueError(f"duplicate rule_id in {path}: {mapping.rule_id}")
        rule_map[mapping.rule_id] = mapping
    return rule_map


def map_finding(finding: StaticFinding, rule_map: RuleMap) -> StaticFinding:
    if not finding.is_a11y:  # regression-only rules (react-hooks) have no WCAG mapping
        return finding
    mapping = rule_map.get(finding.rule_id)
    if mapping is None:
        logger.warning("No WCAG mapping for rule %s; falling back to vector search", finding.rule_id)
        return finding
    return finding.model_copy(update={"wcag_refs": list(mapping.wcag)})


def apply_mapping(result: AnalyzerResult, rule_map: RuleMap | None = None) -> AnalyzerResult:
    """Return a copy of `result` with `wcag_refs` filled. The input is not modified."""
    rule_map = rule_map if rule_map is not None else load_rule_map()
    return result.model_copy(
        update={"findings": [map_finding(f, rule_map) for f in result.findings]}
    )


def wcag_refs_of(result: AnalyzerResult) -> list[str]:
    """Distinct WCAG SC ids across all findings, in first-seen order."""
    seen: dict[str, None] = {}
    for finding in result.a11y_findings:
        for sc in finding.wcag_refs:
            seen.setdefault(sc, None)
    return list(seen)


def apg_patterns_of(result: AnalyzerResult, rule_map: RuleMap | None = None) -> list[str]:
    """Distinct APG patterns implied by the findings' rules, in APG_PATTERNS order."""
    rule_map = rule_map if rule_map is not None else load_rule_map()
    found = {
        rule_map[f.rule_id].apg_pattern
        for f in result.a11y_findings
        if f.rule_id in rule_map and rule_map[f.rule_id].apg_pattern
    }
    return [p for p in APG_PATTERNS if p in found]


def all_mapped_sc(rule_map: RuleMap | None = None) -> set[str]:
    """Every SC referenced by the table (used to check the index covers them)."""
    rule_map = rule_map if rule_map is not None else load_rule_map()
    return {sc for m in rule_map.values() for sc in m.wcag}
