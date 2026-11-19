"""T12: citation checks and the decide step (SERVICE_MVP.md 5.2, 8장). No LLM."""
from __future__ import annotations

import pytest

from a11y_investigator.agent.decision import decide, will_fix
from a11y_investigator.middleware.safety import check_citations, indexed_sc
from a11y_investigator.rag.retriever import RetrievalResult, RetrievedDoc
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.schemas.diagnosis import (
    DiagnosisOutput,
    DocumentEvidence,
    Finding,
    PolicyAssessment,
    StaticEvidence,
)

KNOWN_SC = frozenset({"2.1.1", "4.1.2", "2.4.3"})
RULE = "jsx-a11y/click-events-have-key-events"

ANALYSIS = AnalyzerResult(
    parse_ok=True,
    findings=[StaticFinding(tool="eslint-jsx-a11y", rule_id=RULE, message="m", line=2, wcag_refs=["2.1.1"])],
)
RETRIEVAL = RetrievalResult(
    official=[
        RetrievedDoc(document_id="wcag-2.1.1", text="t", source_type="wcag", title="t", via="exact"),
        RetrievedDoc(document_id="apg-dialog-keyboard", text="t", source_type="apg", title="t", via="exact"),
    ],
    policies=[
        RetrievedDoc(document_id="demo-ds-btn-001", text="t", source_type="project_policy",
                     title="t", project_id="demo-ds", via="policy"),
    ],
)


def doc(doc_id: str, source_type: str = "official") -> DocumentEvidence:
    return DocumentEvidence(document_id=doc_id, source_type=source_type)


def finding(fid="F1", status="confirmed", evidence=None, sc=None, fix_scope=None) -> Finding:
    return Finding(
        id=fid, title="t", description="d", status=status, severity="serious",
        wcag_criteria=sc if sc is not None else ["2.1.1"],
        evidence=evidence if evidence is not None else [
            StaticEvidence(tool="jsx-a11y", rule_id=RULE, line=2), doc("wcag-2.1.1"),
        ],
        fix_scope=fix_scope, recommendation="r",
    )


def run(*findings: Finding, policies=(), analysis=ANALYSIS):
    return decide(
        DiagnosisOutput(findings=list(findings), policy_assessments=list(policies)),
        analysis, RETRIEVAL, known_sc=KNOWN_SC,
    )


# ── Citation checks ─────────────────────────────────────────


def test_valid_finding_kept_and_tool_normalized() -> None:
    d = run(finding())
    f = d.findings[0]
    assert f.status == "confirmed" and f.will_fix
    assert f.evidence[0].tool == "eslint-jsx-a11y"
    assert d.warnings == []
    assert d.needs_improvement


def test_fake_document_and_fake_sc_demoted() -> None:
    fake = finding(evidence=[doc("wcag-9.9.9")], sc=["9.9.9"])
    d = run(fake)
    f = d.findings[0]
    assert f.evidence == [] and f.wcag_criteria == []
    assert f.status == "manual_review" and not f.will_fix
    assert any("wcag-9.9.9" in w for w in d.warnings)
    assert any("9.9.9" in w and "WCAG" in w for w in d.warnings)
    assert not d.needs_improvement


def test_invented_static_rule_removed() -> None:
    f = finding(evidence=[StaticEvidence(tool="eslint-jsx-a11y", rule_id="jsx-a11y/made-up"), doc("wcag-2.1.1")])
    d = run(f)
    assert [e.kind for e in d.findings[0].evidence] == ["document"]
    assert any("made-up" in w for w in d.warnings)


def test_policy_document_counts_as_evidence() -> None:
    f = finding(status="suspected", fix_scope="local",
                evidence=[doc("demo-ds-btn-001", "project_policy")])
    d = run(f)
    assert d.findings[0].status == "suspected" and d.findings[0].will_fix


def test_unknown_policy_assessment_removed() -> None:
    d = run(finding(), policies=[
        PolicyAssessment(policy_id="demo-ds-btn-001", status="violated", note="n"),
        PolicyAssessment(policy_id="other-001", status="compliant", note="n"),
    ])
    assert [p.policy_id for p in d.policy_assessments] == ["demo-ds-btn-001"]
    assert any("other-001" in w for w in d.warnings)


def test_uncovered_static_rule_warned() -> None:
    d = run(finding(evidence=[doc("wcag-2.1.1")]))
    assert any(RULE in w and "반영되지 않음" in w for w in d.warnings)


def test_parse_failure_forbids_confirmed_and_fixing() -> None:
    broken = AnalyzerResult(parse_ok=False, parse_error="x")
    d = run(finding(evidence=[doc("wcag-2.1.1")]), analysis=broken)
    f = d.findings[0]
    assert f.status == "suspected" and not f.will_fix
    assert not d.needs_improvement


# ── Fix decision (5.2) ──────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "scope", "expected"),
    [
        ("confirmed", None, True),
        ("confirmed", "structural", True),
        ("suspected", "local", True),
        ("suspected", "structural", False),
        ("suspected", None, False),  # missing scope = structural
        ("manual_review", "local", False),
    ],
)
def test_will_fix_table(status: str, scope: str | None, expected: bool) -> None:
    assert will_fix(finding(status=status, fix_scope=scope)) is expected


def test_fix_scope_cleared_for_non_suspected() -> None:
    d = run(finding(status="confirmed", fix_scope="local"))
    assert d.findings[0].fix_scope is None


def test_mixed_findings_fix_targets() -> None:
    d = run(
        finding("F1"),
        finding("F2", status="suspected", fix_scope="structural", evidence=[doc("apg-dialog-keyboard")], sc=["2.4.3"]),
        finding("F3", status="suspected", fix_scope="local", evidence=[doc("apg-dialog-keyboard")], sc=["2.1.1"]),
        finding("F4", status="manual_review", evidence=[], sc=[]),
    )
    assert [f.id for f in d.fix_targets] == ["F1", "F3"]
    assert d.needs_improvement


def test_no_findings_means_no_improvement() -> None:
    d = run()
    assert d.findings == [] and not d.needs_improvement


def test_check_citations_does_not_mutate_input() -> None:
    original = DiagnosisOutput(findings=[finding(evidence=[doc("wcag-9.9.9")])])
    check_citations(original, ANALYSIS, {"wcag-2.1.1"}, set(), KNOWN_SC)
    assert original.findings[0].evidence[0].document_id == "wcag-9.9.9"


def test_indexed_sc_from_manifest() -> None:
    sc = indexed_sc()
    assert {"2.1.1", "4.1.2", "2.4.7"} <= sc
    assert "9.9.9" not in sc
