"""Fix chain: prompt | Claude (structured output) -> FixOutput (SERVICE_MVP.md 4.2).

Only findings with `will_fix=True` are sent as fix targets. On a retry the
previous attempt and why it failed (from revalidation, T14) are included.
"""
from __future__ import annotations

import json
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from a11y_investigator.agent.decision import Decision
from a11y_investigator.agent.prompts import FIX_PROMPT
from a11y_investigator.chains.diagnosis import format_documents, format_policies
from a11y_investigator.chains.llm import get_chat_model
from a11y_investigator.rag.retriever import RetrievalResult
from a11y_investigator.schemas.analyzer import CodeType, TargetLevel
from a11y_investigator.schemas.diagnosis import FindingResult, FixOutput

FIX_MAX_TOKENS = 8192  # the whole file is returned


class RetryFeedback(BaseModel):
    """Why the previous fix attempt failed revalidation (filled from ValidationResult in T14)."""

    previous_code: str
    new_violations: list[str] = Field(default_factory=list)  # "rule_id (line N): message"
    remaining_rules: list[str] = Field(default_factory=list)
    blocked_patterns: list[str] = Field(default_factory=list)
    parse_error: str | None = None


# ── Prompt input formatting (pure) ──────────────────────────


def format_findings(findings: list[FindingResult]) -> str:
    if not findings:
        return "(none)"
    blocks = []
    for f in findings:
        rules = [e.rule_id for e in f.evidence if e.kind == "static_analysis"]
        docs = [e.document_id for e in f.evidence if e.kind == "document"]
        blocks.append(
            f"- {f.id} [{f.status}, {f.severity}] {f.title}\n"
            f"  location: {f.location or '-'} | wcag: {', '.join(f.wcag_criteria) or '-'}"
            f" | rules: {', '.join(rules) or '-'} | documents: {', '.join(docs) or '-'}\n"
            f"  problem: {f.description}\n"
            f"  recommendation: {f.recommendation}"
        )
    return "\n".join(blocks)


def format_feedback(feedback: RetryFeedback | None) -> str:
    if feedback is None:
        return ""
    problems = (
        ([f"code does not parse: {feedback.parse_error}"] if feedback.parse_error else [])
        + [f"new violation introduced: {v}" for v in feedback.new_violations]
        + [f"violation still present: {r}" for r in feedback.remaining_rules]
        + [f"forbidden pattern used: {p}" for p in feedback.blocked_patterns]
    )
    return (
        "<previous_attempt>\nYour previous attempt failed revalidation. Fix these problems and "
        "return a corrected complete file.\nProblems:\n"
        + "\n".join(f"- {p}" for p in problems)
        + f"\nPrevious code:\n{feedback.previous_code}\n</previous_attempt>"
    )


def build_inputs(
    code: str,
    code_type: CodeType,
    decision: Decision,
    retrieval: RetrievalResult,
    component_mapping: dict[str, str] | None = None,
    target_level: TargetLevel = "AA",
    feedback: RetryFeedback | None = None,
) -> dict[str, str]:
    return {
        "code_type": code_type,
        "target_level": target_level,
        "code": code,
        "fix_targets": format_findings(decision.fix_targets),
        "not_fixing": format_findings([f for f in decision.findings if not f.will_fix]),
        "component_mapping": json.dumps(component_mapping or {}, ensure_ascii=False),
        "documents": format_documents(retrieval.official),
        "policies": format_policies(retrieval.policies),
        "previous_attempt": format_feedback(feedback),
    }


_FENCE_RE = re.compile(r"^\s*```[^\n]*\n(.*?)\n?```\s*$", re.DOTALL)


def strip_fences(code: str) -> str:
    """Remove a markdown fence if the model wrapped the code in one anyway."""
    match = _FENCE_RE.match(code)
    return (match.group(1) if match else code).strip("\n") + "\n"


# ── Chain ───────────────────────────────────────────────────


def fix_chain(llm: BaseChatModel | None = None) -> Runnable:
    model = llm or get_chat_model(max_tokens=FIX_MAX_TOKENS)
    return FIX_PROMPT | model.with_structured_output(FixOutput)


def generate_fix(
    code: str,
    code_type: CodeType,
    decision: Decision,
    retrieval: RetrievalResult,
    component_mapping: dict[str, str] | None = None,
    target_level: TargetLevel = "AA",
    feedback: RetryFeedback | None = None,
    llm: BaseChatModel | None = None,
) -> FixOutput:
    if not decision.fix_targets:
        raise ValueError("generate_fix called without fix targets (needs_improvement is False)")
    inputs = build_inputs(code, code_type, decision, retrieval, component_mapping, target_level, feedback)
    output: FixOutput = fix_chain(llm).invoke(inputs)
    return output.model_copy(update={"improved_code": strip_fences(output.improved_code)})
