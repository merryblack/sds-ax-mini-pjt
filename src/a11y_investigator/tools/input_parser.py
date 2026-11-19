"""Input parsing: code extraction, code_type, input limits, component hints (SERVICE_MVP.md 2장).

Everything here is deterministic — no LLM calls.
"""
from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel

from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import CodeType, TargetLevel

ErrorCode = Literal["no_code_found", "multiple_code_blocks", "input_too_long", "not_react"]

COMPONENT_ORDER = ("button", "dialog", "tabs", "combobox")


class ParsedInput(BaseModel):
    """Result of `parse_input`. When `ok` is False, `error_code`/`error_message` explain why."""

    ok: bool
    user_request: str = ""
    code: str = ""
    code_type: CodeType | None = None
    component_hint: list[str] | None = None
    requested_level: TargetLevel | None = None  # level named in the request text, if any
    error_code: ErrorCode | None = None
    error_message: str | None = None


# ── 2.4 Code extraction ─────────────────────────────────────

_FENCE_RE = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)
_OPEN_FENCE_RE = re.compile(r"```[^\n`]*\n(.*)\Z", re.DOTALL)
_CODE_START_RE = re.compile(
    r"""^\s*(
        import\b | export\b | function\b | const\b | let\b | var\b | class\b
      | interface\b | type\s+\w+ | async\s+function\b
      | ["']use\ (client|strict)["']
      | //  | /\*                      # a leading comment belongs to the code
      | <
    )""",
    re.VERBOSE,
)


class _ExtractError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def extract_code(raw: str, file_code: str | None = None) -> tuple[str, str]:
    """Return (code, user_request). Raises _ExtractError on failure."""
    if file_code is not None and file_code.strip():
        return file_code.strip("\n"), raw.strip()

    fences = _FENCE_RE.findall(raw)
    if len(fences) >= 2:
        raise _ExtractError(
            "multiple_code_blocks",
            f"코드 블록이 {len(fences)}개 입력되었습니다. 한 번에 하나의 컴포넌트만 분석할 수 있습니다.",
        )
    if len(fences) == 1:
        code = fences[0].strip("\n")
        request = _FENCE_RE.sub("", raw, count=1).strip()
        return code, request

    open_fence = _OPEN_FENCE_RE.search(raw)
    if open_fence:  # opening fence without a closing one
        return open_fence.group(1).strip("\n"), raw[: open_fence.start()].strip()

    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if _CODE_START_RE.match(line):
            code = "\n".join(lines[i:]).strip("\n")
            request = "\n".join(lines[:i]).strip()
            return code, request

    raise _ExtractError("no_code_found", "입력에서 분석할 React 코드를 찾지 못했습니다.")


# ── 2.3 Input limits ────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough upper-bound token estimate for code (~3 characters per token)."""
    return math.ceil(len(text) / 3)


def check_limits(code: str) -> str | None:
    """Return a Korean error message if the code exceeds limits, else None."""
    n_lines = len(code.splitlines())
    if n_lines > settings.max_code_lines:
        return f"코드가 {n_lines}줄입니다. 최대 {settings.max_code_lines}줄까지 분석할 수 있습니다."
    n_tokens = estimate_tokens(code)
    if n_tokens > settings.max_code_tokens:
        return (
            f"코드가 너무 깁니다(약 {n_tokens:,} 토큰). "
            f"최대 약 {settings.max_code_tokens:,} 토큰까지 분석할 수 있습니다."
        )
    return None


# ── 2.1 React / code_type detection ─────────────────────────

_HTML_DOC_RE = re.compile(r"<!doctype\s+html|<html[\s>]|<head[\s>]|<body[\s>]", re.IGNORECASE)
# `class` only as a declaration (`class Foo`), not the HTML attribute `class="..."`
_JS_STRUCTURE_RE = re.compile(r"\b(function|const|let|var|import|export|return)\b|=>|\bclass\s+[A-Z]")
_JSX_RE = re.compile(r"<([A-Za-z][\w.]*)(\s|/?>)|<>")

_TS_PATTERNS = [
    re.compile(r"\binterface\s+[A-Z]\w*"),
    re.compile(r"^\s*(export\s+)?type\s+[A-Z]\w*\s*(<[^>]*>)?\s*=", re.MULTILINE),
    re.compile(r"\bimport\s+type\b"),
    re.compile(r"\bas\s+const\b"),
    # generics on hooks / React types: useState<string>(), React.FC<Props>
    re.compile(r"\b(use[A-Z]\w*|React\.\w+|FC|Ref|RefObject)\s*<[\w\s.,|\[\]<>]+>"),
    # parameter annotations: ({ a, b }: Props) or (e: React.MouseEvent)
    re.compile(r"[(,]\s*(\{[^{}]*\}|\w+)\??\s*:\s*[A-Z][\w.]*(<[^>]*>)?(\[\])?\s*[,)=]"),
    # primitive annotations: x: string, y?: number
    re.compile(r"\b\w+\??\s*:\s*(string|number|boolean|void|unknown|never|any)\b(\[\])?"),
    # return type annotation: ): JSX.Element {  /  ): void =>
    # (must start with a letter so JSX ternaries like `) : <span>{x}` don't match)
    re.compile(r"\)\s*:\s*[A-Za-z][\w.]*(<[^>]*>)?(\[\])?\s*(\{|=>)"),
]


def is_react_code(code: str) -> bool:
    if _HTML_DOC_RE.search(code):
        return False
    return bool(_JSX_RE.search(code)) and bool(_JS_STRUCTURE_RE.search(code))


def detect_code_type(code: str) -> CodeType:
    """'tsx' if TypeScript syntax is present, else 'jsx'. Assumes `is_react_code(code)`."""
    return "tsx" if any(p.search(code) for p in _TS_PATTERNS) else "jsx"


# ── 2.6 Component hints ─────────────────────────────────────

_ROLE_RE = re.compile(r"""\brole\s*=\s*\{?\s*["'`]([\w-]+)["'`]""")
_ROLE_MAP = {
    "button": "button",
    "dialog": "dialog",
    "alertdialog": "dialog",
    "tablist": "tabs",
    "tab": "tabs",
    "tabpanel": "tabs",
    "combobox": "combobox",
    "listbox": "combobox",
}
_NAME_RE = re.compile(r"\b(?:function|const|let|class)\s+([A-Z]\w*)|<([A-Z]\w*)")
_NAME_RULES = [
    (re.compile(r"(Dialog|Modal)"), "dialog"),
    (re.compile(r"(Tabs|TabList|TabPanels?)$|^Tab$"), "tabs"),  # not "Table"
    (re.compile(r"Combo[bB]ox|Auto[cC]omplete|Select$"), "combobox"),  # not "SelectedItem"
    (re.compile(r"Button$"), "button"),
]
_DIALOG_EL_RE = re.compile(r"<dialog[\s>]")
_BUTTON_EL_RE = re.compile(r"<button[\s>]")
_CLICKABLE_EL_RE = re.compile(r"<(div|span|li|p|img|a)\b[^>]*\bonClick\s*=")


def detect_component_hint(code: str) -> list[str] | None:
    hints: set[str] = set()

    for role in _ROLE_RE.findall(code):
        if role in _ROLE_MAP:
            hints.add(_ROLE_MAP[role])

    for decl, tag in _NAME_RE.findall(code):
        name = decl or tag
        for pattern, hint in _NAME_RULES:
            if pattern.search(name):
                hints.add(hint)

    if _DIALOG_EL_RE.search(code):
        hints.add("dialog")
    if _BUTTON_EL_RE.search(code) or _CLICKABLE_EL_RE.search(code):
        hints.add("button")

    ordered = [h for h in COMPONENT_ORDER if h in hints]
    return ordered or None


# ── 2.5 Target level named in the request ──────────────────

_LEVEL_AA_RE = re.compile(r"(?<![A-Za-z])(AAA|AA)(?![A-Za-z])")
_LEVEL_A_RE = re.compile(
    r"(?:레벨|level|등급|수준)\s*A(?![A-Za-z])|(?<![A-Za-z])A\s*(?:레벨|level|등급|수준|기준)",
    re.IGNORECASE,
)


def detect_requested_level(text: str) -> TargetLevel | None:
    match = _LEVEL_AA_RE.search(text)
    if match:
        return match.group(1)  # type: ignore[return-value]
    if _LEVEL_A_RE.search(text):
        return "A"
    return None


# ── Entry point ─────────────────────────────────────────────


def parse_input(raw: str, file_code: str | None = None) -> ParsedInput:
    """Parse user input into code + metadata. Never raises for bad input."""
    try:
        code, user_request = extract_code(raw, file_code)
    except _ExtractError as e:
        return ParsedInput(ok=False, user_request=raw.strip(), error_code=e.code, error_message=e.message)

    requested_level = detect_requested_level(user_request)

    limit_error = check_limits(code)
    if limit_error:
        return ParsedInput(
            ok=False, user_request=user_request, code=code, requested_level=requested_level,
            error_code="input_too_long", error_message=limit_error,
        )

    if not is_react_code(code):
        return ParsedInput(
            ok=False, user_request=user_request, code=code, requested_level=requested_level,
            error_code="not_react",
            error_message="MVP는 React(JSX/TSX) 코드만 지원합니다. HTML 입력은 이후 버전에서 지원합니다.",
        )

    return ParsedInput(
        ok=True,
        user_request=user_request,
        code=code,
        code_type=detect_code_type(code),
        component_hint=detect_component_hint(code),
        requested_level=requested_level,
    )
