"""T17, T20: evaluation dataset / in-out set (SERVICE_MVP.md 9.2).

Schema and reference checks run offline. The `node` test re-runs the real
analyzer to keep `static_rule_ids` labels in sync with what the analyzer reports.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest

from a11y_investigator.middleware.safety import indexed_sc
from a11y_investigator.rag.chunker import official_chunks
from a11y_investigator.tools.policy_lookup import load_policies, load_project
from a11y_investigator.tools.rule_mapping import load_rule_map
from a11y_investigator.tools.static_analysis import analyze_code
from evals.dataset import EvalCase, load_cases

CASES = load_cases()


DIAGNOSIS_SET = [c for c in CASES if c.category in ("positive", "negative") and c.kind != "rejected"
                 and c.component != "other"]
ANALYZED = [c for c in CASES if c.kind != "rejected"]


def test_case_counts_match_spec() -> None:
    """9.2 table (19 diagnosis cases) + T20 in-out additions (30 in total)."""
    assert len(CASES) == 30
    by_component = Counter((c.component, c.kind) for c in DIAGNOSIS_SET)
    assert by_component == {
        ("button", "issue"): 4, ("button", "clean"): 2, ("button", "policy"): 2,
        ("dialog", "issue"): 3, ("dialog", "clean"): 1,
        ("tabs", "issue"): 3, ("tabs", "clean"): 1,
        ("combobox", "issue"): 2, ("combobox", "clean"): 1,
    }
    assert Counter(c.category for c in CASES) == {"positive": 14, "negative": 8, "edge": 4, "guardrail": 4}
    assert sum(c.code_type == "tsx" for c in CASES) >= 4


def test_rejected_cases_never_reach_the_llm() -> None:
    for case in CASES:
        if case.kind == "rejected":
            assert {"diagnose", "generate_fix"} <= set(case.expected.forbidden_nodes), case.id


def test_ids_unique() -> None:
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))


def test_references_exist() -> None:
    """Every label points at something real: rules, SC, documents, policies."""
    rules = set(load_rule_map())
    sc = indexed_sc()
    docs = {c.id for c in official_chunks()}
    for case in CASES:
        exp = case.expected
        assert set(exp.static_rule_ids) <= rules, case.id
        assert {s for f in exp.findings for s in f.wcag_criteria} <= sc, case.id
        assert set(exp.document_ids) <= docs, case.id
        if case.project_id and case.kind != "rejected":
            policies = {p.policy_id: p for p in load_policies(case.project_id)}
            for pa in exp.policy_assessments:
                assert pa.policy_id in policies, (case.id, pa.policy_id)
            applicable = {pid for pid, p in policies.items() if case.component in p.applies_to}
            assert {pa.policy_id for pa in exp.policy_assessments} == applicable, case.id


def test_rule_backed_findings_cite_mapped_sc() -> None:
    """A finding backed by a rule must include at least one SC the mapping table gives that rule."""
    rule_map = load_rule_map()
    for case in CASES:
        for f in case.expected.findings:
            for rule_id in f.rule_ids:
                assert set(rule_map[rule_id].wcag) & set(f.wcag_criteria), (case.id, rule_id)


def test_schema_rejects_inconsistent_labels() -> None:
    base = CASES[0].model_dump()
    clean = {**base, "kind": "clean"}
    with pytest.raises(ValueError, match="clean cases"):
        EvalCase.model_validate(clean)
    orphan = {**base, "expected": {**base["expected"], "findings": []}}
    with pytest.raises(ValueError, match="need expected findings"):
        EvalCase.model_validate(orphan)
    suspected = {**base, "expected": {**base["expected"], "findings": [
        {"description": "d", "status": "suspected", "wcag_criteria": ["4.1.2"]}]}}
    with pytest.raises(ValueError, match="fix_scope"):
        EvalCase.model_validate(suspected)
    both = {**base, "raw_input": "x"}
    with pytest.raises(ValueError, match="exactly one of code / raw_input"):
        EvalCase.model_validate(both)
    rejected = {**base, "kind": "rejected"}
    with pytest.raises(ValueError, match="rejected cases"):
        EvalCase.model_validate(rejected)


def _actual_rules(case: EvalCase) -> list[str] | None:
    mapping = load_project(case.project_id).component_mapping if case.project_id else None
    result = analyze_code(case.code, case.code_type, mapping)
    return sorted({f.rule_id for f in result.a11y_findings}) if result.parse_ok else None


@pytest.mark.node
def test_static_labels_match_analyzer() -> None:
    """One Node process per case, run in parallel (~1.2 s each sequentially)."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual = dict(zip([c.id for c in ANALYZED], pool.map(_actual_rules, ANALYZED)))
    mismatches = {
        c.id: (actual[c.id], sorted(c.expected.static_rule_ids))
        for c in ANALYZED if actual[c.id] != sorted(c.expected.static_rule_ids)
    }
    assert not mismatches, f"case: (analyzer, label) {mismatches}"
