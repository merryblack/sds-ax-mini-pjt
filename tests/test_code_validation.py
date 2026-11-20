"""T14: revalidation (SPEC_MVP.md 5.3, 8장). No LLM.

Logic tests use a fake analyzer; a few tests run the real Node analyzer.
"""
from __future__ import annotations

import pytest

from a11y_investigator.middleware.safety import find_blocked_patterns
from a11y_investigator.schemas.analyzer import AnalyzerResult, StaticFinding
from a11y_investigator.schemas.diagnosis import (
    DocumentEvidence,
    FindingResult,
    StaticEvidence,
    ValidationResult,
)
from a11y_investigator.tools.code_validation import (
    can_retry,
    count_changed_lines,
    feedback_from,
    validate_generated_code,
)

from samples import FIXED_A, SCENARIO_A  # noqa: E402

CLICK = "jsx-a11y/click-events-have-key-events"
STATIC = "jsx-a11y/no-static-element-interactions"
NONINT = "jsx-a11y/no-noninteractive-element-interactions"


def sf(rule: str, line: int = 2) -> StaticFinding:
    return StaticFinding(tool="eslint-jsx-a11y", rule_id=rule, message=f"msg {rule}", line=line, element="div")


def target(*rules: str) -> FindingResult:
    return FindingResult(
        id="F1", title="t", description="d", status="confirmed", severity="serious",
        wcag_criteria=["2.1.1"],
        evidence=[*(StaticEvidence(tool="eslint-jsx-a11y", rule_id=r) for r in rules),
                  DocumentEvidence(document_id="wcag-2.1.1", source_type="official")],
        recommendation="r", will_fix=True,
    )


ORIGINAL = AnalyzerResult(parse_ok=True, findings=[sf(CLICK), sf(STATIC)])


def fake(result: AnalyzerResult):
    return lambda code, code_type, mapping: result


def validate(after: AnalyzerResult, improved="<button />", original="<div onClick={f} />", targets=None, attempt=1):
    return validate_generated_code(
        original, improved, "jsx", ORIGINAL, targets or [target(CLICK, STATIC)],
        attempt=attempt, analyzer=fake(after),
    )


# ── Pass criteria with a fake analyzer ──────────────────────


def test_passes_when_target_rules_resolved() -> None:
    v, _ = validate(AnalyzerResult(parse_ok=True))
    assert v.status == "passed"
    assert (v.findings_before, v.findings_after) == (2, 0)
    assert v.new_findings == [] and v.remaining_rule_ids == [] and v.blocked_patterns == []


def test_fails_on_parse_error() -> None:
    v, after = validate(AnalyzerResult(parse_ok=False, parse_error="Unexpected token (1:3)"))
    assert v.status == "failed"
    assert feedback_from(v, "<b", after).parse_error == "Unexpected token (1:3)"


def test_fails_on_new_rule() -> None:
    v, _ = validate(AnalyzerResult(parse_ok=True, findings=[sf(NONINT, 7)]))
    assert v.status == "failed"
    assert [f.rule_id for f in v.new_findings] == [NONINT]


def test_rule_count_increase_counts_as_new() -> None:
    """Same rule as before, but more occurrences = a new violation."""
    original_two = AnalyzerResult(parse_ok=True, findings=[sf("jsx-a11y/alt-text")])
    v, _ = validate_generated_code(
        "<img />", "<img /><img />", "jsx", original_two, [target(CLICK)],
        analyzer=fake(AnalyzerResult(parse_ok=True, findings=[sf("jsx-a11y/alt-text"), sf("jsx-a11y/alt-text", 3)])),
    )
    assert v.status == "failed" and len(v.new_findings) == 2


def test_untouched_non_target_violation_is_ok() -> None:
    """A violation that existed before and is not a fix target does not fail validation."""
    original = AnalyzerResult(parse_ok=True, findings=[sf(CLICK), sf("jsx-a11y/alt-text")])
    v, _ = validate_generated_code(
        "o", "i", "jsx", original, [target(CLICK)],
        analyzer=fake(AnalyzerResult(parse_ok=True, findings=[sf("jsx-a11y/alt-text")])),
    )
    assert v.status == "passed"


def test_fails_when_target_rule_remains() -> None:
    v, after = validate(AnalyzerResult(parse_ok=True, findings=[sf(CLICK)]))
    assert v.status == "failed" and v.remaining_rule_ids == [CLICK]
    assert feedback_from(v, "<div />", after).remaining_rules == [CLICK]


def test_fails_on_eslint_disable() -> None:
    v, after = validate(
        AnalyzerResult(parse_ok=True),
        improved="// eslint-disable-next-line jsx-a11y/click-events-have-key-events\n<div onClick={f} />",
    )
    assert v.status == "failed" and v.blocked_patterns == ["eslint-disable"]
    assert feedback_from(v, "x", after).blocked_patterns == ["eslint-disable"]


def test_feedback_describes_new_violation() -> None:
    v, after = validate(AnalyzerResult(parse_ok=True, findings=[sf(NONINT, 7)]))
    fb = feedback_from(v, "previous", after)
    assert fb.new_violations == [f"{NONINT} (line 7, <div>): msg {NONINT}"]
    assert fb.previous_code == "previous"


# ── Helpers ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("original", "improved", "expected"),
    [
        ("// eslint-disable-next-line x\na", "// eslint-disable-next-line x\nb", []),  # pre-existing
        ("a", "/* eslint-disable */\na", ["eslint-disable"]),
        ("a", "a // eslint-disable-line", ["eslint-disable"]),
        ("a", "// @ts-ignore\na", ["@ts-ignore / @ts-nocheck"]),
        ("a", "const disabled = true;", []),
    ],
)
def test_find_blocked_patterns(original: str, improved: str, expected: list[str]) -> None:
    assert find_blocked_patterns(original, improved) == expected


def test_count_changed_lines() -> None:
    assert count_changed_lines("a\nb\nc", "a\nb\nc") == 0
    assert count_changed_lines("a\nb\nc", "a\nX\nc") == 1
    assert count_changed_lines("a\nb", "import y;\n\na\nb") == 2
    assert count_changed_lines("  a\nb", "a\nb\n") == 0  # whitespace-only


def test_can_retry_limits_attempts() -> None:
    failed = lambda n: ValidationResult(status="failed", attempts=n)  # noqa: E731
    assert can_retry(failed(1)) and can_retry(failed(2))
    assert not can_retry(failed(3))
    assert not can_retry(ValidationResult(status="passed", attempts=1))


# ── Real analyzer ───────────────────────────────────────────

DIALOG_FIX_WITH_KEYDOWN = """export function ConfirmDialog({ open, onClose }) {
  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <button onClick={onClose}>취소</button>
    </div>
  );
}
"""
DIALOG_ORIGINAL = """export function ConfirmDialog({ open, onClose }) {
  if (!open) return null;
  return (
    <div className="dialog">
      <button onClick={onClose}>취소</button>
    </div>
  );
}
"""


@pytest.mark.node
def test_real_scenario_a_fix_passes() -> None:
    from a11y_investigator.tools.static_analysis import analyze_code

    original = analyze_code(SCENARIO_A, "jsx")
    v, _ = validate_generated_code(SCENARIO_A, FIXED_A, "jsx", original, [target(CLICK, STATIC)])
    assert v.status == "passed" and v.changed_lines == 1


@pytest.mark.node
@pytest.mark.llm
def test_retry_with_feedback_resolves_new_violation() -> None:
    """Attempt 1 (onKeyDown on role=dialog) fails; feedback makes attempt 2 pass."""
    from a11y_investigator.agent.decision import Decision
    from a11y_investigator.chains.improvement import generate_fix
    from a11y_investigator.rag.retriever import retrieve
    from a11y_investigator.tools.rule_mapping import apply_mapping
    from a11y_investigator.tools.static_analysis import analyze_code

    original = apply_mapping(analyze_code(DIALOG_ORIGINAL, "jsx"))
    escape = FindingResult(
        id="F1", title="Escape 키로 닫기 미구현", description="Escape 키 처리 없음",
        status="suspected", severity="serious", wcag_criteria=["2.1.1"], fix_scope="local",
        evidence=[DocumentEvidence(document_id="apg-dialog-keyboard", source_type="official")],
        recommendation="Escape 키로 onClose 호출", will_fix=True,
    )
    v1, after1 = validate_generated_code(DIALOG_ORIGINAL, DIALOG_FIX_WITH_KEYDOWN, "jsx", original, [escape])
    assert v1.status == "failed"
    fix2 = generate_fix(
        DIALOG_ORIGINAL, "jsx", Decision(findings=[escape], needs_improvement=True),
        retrieve(original, ["dialog"]), feedback=feedback_from(v1, DIALOG_FIX_WITH_KEYDOWN, after1),
    )
    v2, _ = validate_generated_code(DIALOG_ORIGINAL, fix2.improved_code, "jsx", original, [escape], attempt=2)
    assert v2.status == "passed", v2
    assert "Escape" in fix2.improved_code


DIALOG_FIX_HOOK_AFTER_RETURN = """import { useEffect } from "react";

export function ConfirmDialog({ open, onClose }) {
  if (!open) return null;

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div role="dialog" aria-modal="true">
      <button onClick={onClose}>취소</button>
    </div>
  );
}
"""


@pytest.mark.node
def test_real_hook_after_early_return_fails() -> None:
    """The T14 retry output: useEffect after `if (!open) return null` breaks the Rules of Hooks."""
    from a11y_investigator.tools.static_analysis import analyze_code

    original = analyze_code(DIALOG_ORIGINAL, "jsx")
    v, after = validate_generated_code(DIALOG_ORIGINAL, DIALOG_FIX_HOOK_AFTER_RETURN, "jsx", original, [])
    assert v.status == "failed"
    assert [(f.tool, f.rule_id) for f in v.new_findings] == [("eslint-react-hooks", "react-hooks/rules-of-hooks")]
    assert "called conditionally" in feedback_from(v, "x", after).new_violations[0]


@pytest.mark.node
def test_real_dialog_keydown_fix_fails_with_new_violation() -> None:
    """The T13 Dialog case: onKeyDown on a role=dialog div introduces a new rule violation."""
    from a11y_investigator.tools.static_analysis import analyze_code

    original = analyze_code(DIALOG_ORIGINAL, "jsx")
    assert original.findings == []
    v, _ = validate_generated_code(DIALOG_ORIGINAL, DIALOG_FIX_WITH_KEYDOWN, "jsx", original, [])
    assert v.status == "failed"
    assert [f.rule_id for f in v.new_findings] == [NONINT]
