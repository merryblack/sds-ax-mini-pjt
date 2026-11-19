"""Pipeline fakes shared by test_graph and test_cli (no Node, no Bedrock)."""
from __future__ import annotations

from a11y_investigator.agent import nodes
from a11y_investigator.rag.retriever import RetrievalResult, RetrievedDoc
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.schemas.diagnosis import (
    CodeChange,
    DiagnosisOutput,
    DocumentEvidence,
    Finding,
    FixOutput,
    StaticEvidence,
)

RULE = "jsx-a11y/click-events-have-key-events"
NONINT = "jsx-a11y/no-noninteractive-element-interactions"


def finding(status="confirmed", rule=RULE, fix_scope=None) -> Finding:
    evidence = [DocumentEvidence(document_id="wcag-2.1.1", source_type="official")]
    if rule:
        evidence.insert(0, StaticEvidence(tool="eslint-jsx-a11y", rule_id=rule))
    return Finding(
        id="F1", title="키보드 접근 불가", description="d", status=status, severity="serious",
        wcag_criteria=["2.1.1"], fix_scope=fix_scope, evidence=evidence, recommendation="r",
    )


class Fakes:
    """Configurable stand-ins for analyzer / retriever / LLM chains."""

    def __init__(self, monkeypatch, diagnosis: DiagnosisOutput, fixes: list[str], after: dict[str, list[str]]):
        self.fix_calls: list = []
        self.after = after  # improved code -> rule ids found when re-analyzed

        def analyze(code, code_type, mapping=None):
            if code in self.after:
                return AnalyzerResult(parse_ok=True, findings=[
                    StaticFinding(tool="eslint-jsx-a11y", rule_id=r, message="m", line=2) for r in self.after[code]
                ])
            return AnalyzerResult(
                parse_ok=True,
                findings=[StaticFinding(tool="eslint-jsx-a11y", rule_id=RULE, message="m", line=2)]
                if "<div onClick" in code else [],
                analyzer_versions={"eslint": "9"},
            )

        def retrieve(result, hint, project_id):
            return RetrievalResult(official=[RetrievedDoc(
                document_id="wcag-2.1.1", text="t", source_type="wcag", title="2.1.1",
                source_url="https://www.w3.org/TR/WCAG22/#keyboard", via="exact")])

        def fix(code, code_type, decision, retrieval, mapping, level, feedback):
            self.fix_calls.append(feedback)
            return FixOutput(improved_code=fixes[len(self.fix_calls) - 1], changes=[CodeChange(finding_ids=["F1"], description="버튼")])

        monkeypatch.setattr(nodes, "analyze_code", analyze)
        monkeypatch.setattr(nodes, "retrieve_docs", retrieve)
        monkeypatch.setattr(nodes, "run_diagnosis", lambda *a, **k: diagnosis)
        monkeypatch.setattr(nodes, "run_fix", fix)
        monkeypatch.setattr(nodes, "ensure_policies", lambda pid: False)
