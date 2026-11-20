"""Revalidation of generated code (SPEC_MVP.md 5.3). No LLM.

Pass criteria (all must hold):
1. The improved code parses.
2. No rule gets more violations than in the original (compared per rule_id —
   line numbers move after a fix, so per-line matching is unreliable).
3. Every rule linked to a fix target (static evidence of will_fix findings) is gone.
4. No new lint-bypass comment (eslint-disable etc.).

`changed_lines` is recorded so unnecessary edits are visible in reports and evals.
"""
from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Callable

from a11y_investigator.chains.improvement import RetryFeedback
from a11y_investigator.config import settings
from a11y_investigator.middleware.safety import find_blocked_patterns
from a11y_investigator.schemas.analyzer import AnalyzerResult, CodeType
from a11y_investigator.schemas.diagnosis import FindingResult, StaticEvidence, ValidationResult
from a11y_investigator.tools.static_analysis import analyze_code

Analyzer = Callable[[str, CodeType, dict[str, str] | None], AnalyzerResult]


def count_changed_lines(original: str, improved: str) -> int:
    """Lines touched by the edit (replaced, inserted, or deleted), whitespace-only changes ignored."""
    a = [line.strip() for line in original.strip("\n").splitlines()]
    b = [line.strip() for line in improved.strip("\n").splitlines()]
    changed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    return changed


def target_rules(fix_targets: list[FindingResult]) -> set[str]:
    return {
        ev.rule_id
        for f in fix_targets
        for ev in f.evidence
        if isinstance(ev, StaticEvidence)
    }


def validate_generated_code(
    original_code: str,
    improved_code: str,
    code_type: CodeType,
    original_analysis: AnalyzerResult,
    fix_targets: list[FindingResult],
    component_mapping: dict[str, str] | None = None,
    attempt: int = 1,
    analyzer: Analyzer = analyze_code,
) -> tuple[ValidationResult, AnalyzerResult]:
    """Re-analyze `improved_code` with the same analyzer settings and apply the pass criteria."""
    after = analyzer(improved_code, code_type, component_mapping)
    blocked = find_blocked_patterns(original_code, improved_code)
    changed = count_changed_lines(original_code, improved_code)

    if not after.parse_ok:
        return (
            ValidationResult(
                status="failed", attempts=attempt,
                findings_before=len(original_analysis.findings), findings_after=0,
                blocked_patterns=blocked, changed_lines=changed,
            ),
            after,
        )

    before_counts = Counter(f.rule_id for f in original_analysis.findings)
    after_counts = Counter(f.rule_id for f in after.findings)
    increased = {rule for rule, n in after_counts.items() if n > before_counts.get(rule, 0)}
    new_findings = [f for f in after.findings if f.rule_id in increased]
    remaining = sorted(target_rules(fix_targets) & set(after_counts))

    passed = not new_findings and not remaining and not blocked
    return (
        ValidationResult(
            status="passed" if passed else "failed",
            attempts=attempt,
            findings_before=len(original_analysis.findings),
            findings_after=len(after.findings),
            new_findings=new_findings,
            remaining_rule_ids=remaining,
            blocked_patterns=blocked,
            changed_lines=changed,
        ),
        after,
    )


def can_retry(validation: ValidationResult) -> bool:
    """True if another fix attempt is allowed (max 1 + max_fix_retries attempts)."""
    return validation.status == "failed" and validation.attempts < 1 + settings.max_fix_retries


def feedback_from(
    validation: ValidationResult, previous_code: str, after: AnalyzerResult
) -> RetryFeedback:
    """Turn a failed validation into feedback for the next fix attempt."""
    return RetryFeedback(
        previous_code=previous_code,
        new_violations=[
            f"{f.rule_id} (line {f.line}, <{f.element or '?'}>): {f.message}"
            for f in validation.new_findings
        ],
        remaining_rules=validation.remaining_rule_ids,
        blocked_patterns=validation.blocked_patterns,
        parse_error=None if after.parse_ok else after.parse_error,
    )
