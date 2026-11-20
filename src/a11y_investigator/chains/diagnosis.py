"""Diagnosis chain: prompt | Claude (structured output) -> DiagnosisOutput (SPEC_MVP.md 4.2).

This chain only produces the LLM's diagnosis. Citation checks, demotion of
unsupported findings, and the fix decision happen afterwards in plain code (T12).
"""
from __future__ import annotations

from html import escape

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from a11y_investigator.agent.prompts import DIAGNOSIS_PROMPT
from a11y_investigator.chains.llm import get_chat_model
from a11y_investigator.rag.retriever import RetrievalResult, RetrievedDoc
from a11y_investigator.schemas.analyzer import AnalyzerResult, CodeType, TargetLevel
from a11y_investigator.schemas.diagnosis import DiagnosisOutput


# ── Prompt input formatting (pure) ──────────────────────────


def number_lines(code: str) -> str:
    lines = code.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(lines, start=1))


def format_static(result: AnalyzerResult) -> str:
    if not result.parse_ok:
        return f"PARSE ERROR: {result.parse_error}\n(no rule results; no finding may be 'confirmed')"
    if not result.a11y_findings:
        return "(no rule violations)"
    return "\n".join(
        f"- rule_id={f.rule_id} line={f.line} element={f.element} "
        f"wcag={','.join(f.wcag_refs) or '-'} message={f.message}"
        for f in result.a11y_findings
    )


def _attrs(doc: RetrievedDoc) -> str:
    sc = ",".join(doc.wcag_sc)
    return (
        f'id="{escape(doc.document_id)}" type="{doc.source_type}" '
        f'title="{escape(doc.title)}"' + (f' wcag="{sc}"' if sc else "")
    )


def format_documents(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "<documents>(none)</documents>"
    body = "\n".join(f"<document {_attrs(d)}>\n{d.text}\n</document>" for d in docs)
    return f"<documents>\n{body}\n</documents>"


def format_policies(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "<policies>(no project policies)</policies>"
    body = "\n".join(f'<policy id="{escape(d.document_id)}">\n{d.text}\n</policy>' for d in docs)
    return f"<policies>\n{body}\n</policies>"


def build_inputs(
    code: str,
    code_type: CodeType,
    analysis: AnalyzerResult,
    retrieval: RetrievalResult,
    target_level: TargetLevel = "AA",
    user_request: str = "",
) -> dict[str, str]:
    return {
        "target_level": target_level,
        "code_type": code_type,
        "user_request": user_request.strip() or "(none)",
        "numbered_code": number_lines(code),
        "parse_ok": str(analysis.parse_ok).lower(),
        "static_findings": format_static(analysis),
        "documents": format_documents(retrieval.official),
        "policies": format_policies(retrieval.policies),
    }


# ── Chain ───────────────────────────────────────────────────


def diagnosis_chain(llm: BaseChatModel | None = None) -> Runnable:
    model = llm or get_chat_model()
    return DIAGNOSIS_PROMPT | model.with_structured_output(DiagnosisOutput)


def diagnose(
    code: str,
    code_type: CodeType,
    analysis: AnalyzerResult,
    retrieval: RetrievalResult,
    target_level: TargetLevel = "AA",
    user_request: str = "",
    llm: BaseChatModel | None = None,
) -> DiagnosisOutput:
    inputs = build_inputs(code, code_type, analysis, retrieval, target_level, user_request)
    return diagnosis_chain(llm).invoke(inputs)
