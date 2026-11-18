"""T04: input parser (SERVICE_MVP.md 2장)."""
from __future__ import annotations

import pytest

from a11y_investigator.tools.input_parser import (
    detect_code_type,
    detect_component_hint,
    detect_requested_level,
    parse_input,
)

SCENARIO_A = """export default function SaveButton() {
  return <div onClick={() => alert("saved")}>저장</div>;
}"""

TSX_DIALOG = """import { useState } from "react";

interface ConfirmDialogProps {
  title: string;
  onClose: () => void;
}

export function ConfirmDialog({ title, onClose }: ConfirmDialogProps) {
  const [open, setOpen] = useState<boolean>(true);
  return open ? (
    <div role="dialog" aria-modal="true">
      <h2>{title}</h2>
      <button onClick={onClose}>닫기</button>
    </div>
  ) : null;
}"""


def fenced(code: str, lang: str = "jsx") -> str:
    return f"```{lang}\n{code}\n```"


# ── Extraction (2.4) ────────────────────────────────────────


def test_scenario_a_in_fence() -> None:
    raw = "다음 버튼의 접근성을 검토해 줘.\n\n" + fenced(SCENARIO_A)
    result = parse_input(raw)
    assert result.ok
    assert result.code == SCENARIO_A
    assert result.user_request == "다음 버튼의 접근성을 검토해 줘."
    assert result.code_type == "jsx"
    assert result.component_hint == ["button"]


def test_file_code_takes_priority() -> None:
    result = parse_input("이 파일 검사해 줘 " + fenced("const x = <p />;"), file_code=SCENARIO_A)
    assert result.ok
    assert result.code == SCENARIO_A


def test_multiple_fences_rejected() -> None:
    raw = fenced(SCENARIO_A) + "\n그리고\n" + fenced(TSX_DIALOG, "tsx")
    result = parse_input(raw)
    assert not result.ok
    assert result.error_code == "multiple_code_blocks"


def test_no_fence_starts_at_code_line() -> None:
    raw = "이 컴포넌트 고쳐 줘\n" + SCENARIO_A
    result = parse_input(raw)
    assert result.ok
    assert result.user_request == "이 컴포넌트 고쳐 줘"
    assert result.code.startswith("export default function")


def test_unclosed_fence_takes_rest() -> None:
    result = parse_input("검토해 줘\n```jsx\n" + SCENARIO_A)
    assert result.ok
    assert result.code == SCENARIO_A


def test_no_code_found() -> None:
    result = parse_input("버튼 접근성 기준이 뭐야?")
    assert not result.ok
    assert result.error_code == "no_code_found"


# ── Limits (2.3) ────────────────────────────────────────────


def test_too_many_lines() -> None:
    code = "export function A() {\n" + "  const x = 1;\n" * 300 + "  return <div />;\n}"
    result = parse_input(fenced(code))
    assert not result.ok
    assert result.error_code == "input_too_long"
    assert "300" in (result.error_message or "")


def test_too_many_tokens() -> None:
    code = "export const A = () => <p>" + "가" * 30_000 + "</p>;"
    result = parse_input(fenced(code))
    assert not result.ok
    assert result.error_code == "input_too_long"


# ── React / code_type (2.1) ─────────────────────────────────


def test_html_document_rejected() -> None:
    html = "<!DOCTYPE html>\n<html><body><div onclick=\"go()\">Go</div></body></html>"
    result = parse_input(fenced(html, "html"))
    assert not result.ok
    assert result.error_code == "not_react"


def test_plain_html_snippet_rejected() -> None:
    result = parse_input(fenced('<div class="btn" onclick="save()">저장</div>', "html"))
    assert not result.ok
    assert result.error_code == "not_react"


def test_plain_js_without_jsx_rejected() -> None:
    result = parse_input(fenced("function add(a, b) { return a + b; }", "js"))
    assert not result.ok
    assert result.error_code == "not_react"


@pytest.mark.parametrize(
    "code",
    [
        TSX_DIALOG,
        "type Props = { label: string };\nexport const B = (p: Props) => <button>{p.label}</button>;",
        "export const C = (): JSX.Element => <div />;",
        'import type { FC } from "react";\nexport const D: FC = () => <div />;',
        "export function E() { const r = useRef<HTMLDivElement>(null); return <div ref={r} />; }",
    ],
)
def test_detects_tsx(code: str) -> None:
    assert detect_code_type(code) == "tsx"


@pytest.mark.parametrize(
    "code",
    [
        SCENARIO_A,
        "export function F({ open }) { return open ? (<p>a</p>) : <span>{open}</span>; }",
        "const style = { color: 'red' };\nexport const G = () => <p style={style}>Type: text</p>;",
    ],
)
def test_detects_jsx(code: str) -> None:
    assert detect_code_type(code) == "jsx"


# ── Component hint (2.6) ────────────────────────────────────


def test_hint_dialog_from_role_and_button() -> None:
    assert detect_component_hint(TSX_DIALOG) == ["button", "dialog"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ('export function SettingsTabs() { return <div role="tablist" />; }', ["tabs"]),
        ("export const CountrySelect = () => <input role={'combobox'} />;", ["combobox"]),
        ("export function Modal() { return <dialog open />; }", ["dialog"]),
        ("export function DataTable() { return <table />; }", None),
        ("export function SelectedItem() { return <p />; }", None),
    ],
)
def test_component_hints(code: str, expected: list[str] | None) -> None:
    assert detect_component_hint(code) == expected


# ── Requested level (2.5) ───────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AAA 기준으로 검사해 줘", "AAA"),
        ("WCAG 2.2 AA를 기준으로", "AA"),
        ("레벨 A만 확인해 줘", "A"),
        ("WCAG 2.2를 기준으로 검사해 줘", None),
        ("a11y 점검 부탁해", None),
    ],
)
def test_requested_level(text: str, expected: str | None) -> None:
    assert detect_requested_level(text) == expected


def test_level_parsed_from_request_not_code() -> None:
    result = parse_input("AAA 기준으로 봐 줘\n" + fenced(SCENARIO_A))
    assert result.requested_level == "AAA"
