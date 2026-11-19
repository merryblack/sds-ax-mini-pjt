"""T07: rule -> WCAG mapping (SERVICE_MVP.md 6.3)."""
from __future__ import annotations

import json
import logging
import subprocess

import pytest

from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.tools.rule_mapping import (
    all_mapped_sc,
    apg_patterns_of,
    apply_mapping,
    load_rule_map,
    wcag_refs_of,
)
from a11y_investigator.tools.static_analysis import StaticAnalysisError, find_node


def finding(rule_id: str) -> StaticFinding:
    return StaticFinding(tool="eslint-jsx-a11y", rule_id=rule_id, message="m", element="div")


SCENARIO_A = AnalyzerResult(
    parse_ok=True,
    findings=[
        finding("jsx-a11y/click-events-have-key-events"),
        finding("jsx-a11y/no-static-element-interactions"),
    ],
)


def test_table_loads_all_recommended_rules() -> None:
    rule_map = load_rule_map()
    assert len(rule_map) == 31
    assert all(rid.startswith("jsx-a11y/") for rid in rule_map)


def test_table_matches_enabled_analyzer_rules() -> None:
    """Every rule the analyzer can report must be mapped, and nothing extra."""
    try:
        node = find_node()
    except StaticAnalysisError:
        pytest.skip("Node.js not installed")
    script = (
        "import p from 'eslint-plugin-jsx-a11y';"
        "const r = p.flatConfigs.recommended.rules;"
        "console.log(JSON.stringify(Object.entries(r)"
        ".filter(([, v]) => (Array.isArray(v) ? v[0] : v) !== 'off').map(([k]) => k)));"
    )
    out = subprocess.run(
        [str(node), "--input-type=module", "-e", script],
        cwd=settings.analyzer_dir, capture_output=True, text=True, check=True,
    ).stdout
    assert set(json.loads(out)) == set(load_rule_map())


def test_apply_mapping_fills_wcag_refs_without_mutating() -> None:
    mapped = apply_mapping(SCENARIO_A)
    assert [f.wcag_refs for f in mapped.findings] == [["2.1.1"], ["2.1.1", "4.1.2"]]
    assert all(f.wcag_refs == [] for f in SCENARIO_A.findings)


def test_unmapped_rule_warns_and_stays_empty(caplog: pytest.LogCaptureFixture) -> None:
    result = AnalyzerResult(parse_ok=True, findings=[finding("jsx-a11y/brand-new-rule")])
    with caplog.at_level(logging.WARNING):
        mapped = apply_mapping(result)
    assert mapped.findings[0].wcag_refs == []
    assert "brand-new-rule" in caplog.text


def test_wcag_refs_and_apg_patterns_of_scenario_a() -> None:
    mapped = apply_mapping(SCENARIO_A)
    assert wcag_refs_of(mapped) == ["2.1.1", "4.1.2"]
    assert apg_patterns_of(mapped) == ["button"]


def test_all_mapped_sc_is_small_and_well_formed() -> None:
    scs = all_mapped_sc()
    assert {"1.1.1", "2.1.1", "2.4.3", "4.1.2"} <= scs
    assert len(scs) < 20


def test_duplicate_rule_rejected(tmp_path) -> None:
    path = tmp_path / "map.yaml"
    entry = "  - {rule_id: r, tool: t, wcag: ['2.1.1'], default_severity: minor}\n"
    path.write_text("rules:\n" + entry * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_rule_map(path)


@pytest.mark.parametrize(
    "bad",
    [
        "{rule_id: r, tool: t, wcag: ['2.1'], default_severity: minor}",
        "{rule_id: r, tool: t, wcag: [], apg_pattern: carousel, default_severity: minor}",
        "{rule_id: r, tool: t, wcag: [], default_severity: blocker}",
    ],
)
def test_bad_entries_rejected(tmp_path, bad: str) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(f"rules:\n  - {bad}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_rule_map(path)


def test_regression_findings_are_not_mapped_or_warned(caplog: pytest.LogCaptureFixture) -> None:
    hooks = StaticFinding(tool="eslint-react-hooks", rule_id="react-hooks/rules-of-hooks", message="m")
    result = AnalyzerResult(parse_ok=True, findings=[finding("jsx-a11y/alt-text"), hooks])
    with caplog.at_level(logging.WARNING):
        mapped = apply_mapping(result)
    assert "rules-of-hooks" not in caplog.text
    assert mapped.findings[1].wcag_refs == []
    assert [f.rule_id for f in mapped.a11y_findings] == ["jsx-a11y/alt-text"]
    assert [f.rule_id for f in mapped.regression_findings] == ["react-hooks/rules-of-hooks"]
    assert wcag_refs_of(mapped) == ["1.1.1"]
