"""A11y Investigator 실행기. 가상환경을 활성화하지 않고 CLI를 실행한다.

    python a11y.py analyze --file examples/save_button.jsx --project demo-ds
    python a11y.py policies check demo-ds
    python a11y.py --help

개발용 단축 명령(저장소 폴더에서 실행):

    python a11y.py test [pytest 인자]          # 예: python a11y.py test --no-node
    python a11y.py eval [evals.evaluate 인자]  # 예: python a11y.py eval --case guardrail --no-ragas
    python a11y.py index [--policies]         # 검색 인덱스 다시 만들기 (rag.ingest)
    python a11y.py fetch                      # W3C 원문 다시 받기 (rag.fetch)

모든 인자와 표준 입력을 `.venv`의 Python으로 그대로 넘기고, 종료 코드를 유지한다.
먼저 `python setup_env.py`로 설치해야 한다.
"""
from __future__ import annotations

import subprocess
import sys

from setup_env import ROOT, venv_python

DEV_COMMANDS = {
    "test": ["-m", "pytest"],
    "eval": ["-m", "evals.evaluate"],
    "index": ["-m", "a11y_investigator.rag.ingest"],
    "fetch": ["-m", "a11y_investigator.rag.fetch"],
}


def build_command(argv: list[str]) -> tuple[list[str], str | None]:
    """Arguments for the venv Python, and the working directory (None = keep the caller's)."""
    if argv and argv[0] in DEV_COMMANDS:
        return [*DEV_COMMANDS[argv[0]], *argv[1:]], str(ROOT)
    return ["-m", "a11y_investigator", *argv], None


def main(argv: list[str]) -> int:
    python = venv_python()
    if not python.exists():
        print("아직 설치되지 않았습니다. 먼저 `python setup_env.py`를 실행하세요.", file=sys.stderr)
        return 1
    args, cwd = build_command(argv)
    try:
        return subprocess.call([str(python), *args], cwd=cwd)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
