"""Run the Node analyzer (analyzer-js/analyze.mjs) via subprocess (SERVICE_MVP.md 5.1).

Code goes in on stdin, one AnalyzerResult JSON comes back on stdout.
Any failure to run the analyzer raises `StaticAnalysisError`; the graph node turns
that into `outcome=analysis_failed`. A *parse error in the user's code* is not a
failure here — it comes back as `AnalyzerResult(parse_ok=False)`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from a11y_investigator.config import settings
from a11y_investigator.schemas.analyzer import AnalyzerResult, CodeType

ErrorKind = Literal["node_not_found", "analyzer_not_installed", "timeout", "analyzer_failed", "bad_output"]

_WINDOWS_DEFAULT_NODE = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe"


class StaticAnalysisError(Exception):
    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


def find_node(node_bin: str | None = None) -> Path:
    """Resolve the Node.js executable: explicit arg > NODE_BIN > PATH > default Windows install."""
    candidates = [node_bin, settings.node_bin, shutil.which("node"), str(_WINDOWS_DEFAULT_NODE)]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise StaticAnalysisError(
        "node_not_found", "Node.js를 찾을 수 없습니다. 설치하거나 NODE_BIN 환경변수로 경로를 지정하세요."
    )


def analyze_code(
    code: str,
    code_type: CodeType,
    component_mapping: dict[str, str] | None = None,
    *,
    timeout: float | None = None,
    node_bin: str | None = None,
) -> AnalyzerResult:
    """Statically analyze React code with ESLint + jsx-a11y."""
    analyzer_dir = settings.analyzer_dir
    script = analyzer_dir / "analyze.mjs"
    if not (analyzer_dir / "node_modules").is_dir():
        raise StaticAnalysisError(
            "analyzer_not_installed", f"{analyzer_dir}에서 `npm install`을 먼저 실행하세요."
        )

    args = [str(find_node(node_bin)), str(script), "--type", code_type]
    if component_mapping:
        args += ["--components", json.dumps(component_mapping)]

    try:
        proc = subprocess.run(
            args,
            input=code.encode("utf-8"),
            capture_output=True,
            cwd=analyzer_dir,
            timeout=timeout if timeout is not None else settings.analyzer_timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise StaticAnalysisError("timeout", f"정적 분석이 {e.timeout}초 안에 끝나지 않았습니다.") from e

    stderr = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise StaticAnalysisError(
            "analyzer_failed", f"분석기가 종료 코드 {proc.returncode}로 실패했습니다: {stderr[:500]}"
        )

    try:
        return AnalyzerResult.model_validate_json(proc.stdout.decode("utf-8"))
    except (ValidationError, UnicodeDecodeError) as e:
        raise StaticAnalysisError("bad_output", f"분석기 출력을 해석할 수 없습니다: {e}") from e
