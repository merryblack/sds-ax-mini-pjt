"""A11y Investigator 설치 스크립트. 모든 OS·셸에서 같은 명령으로 실행한다.

    python setup_env.py          # 설치 (여러 번 실행해도 안전, 끝난 단계는 건너뜀)
    python setup_env.py --yes    # 질문 없이 검색 인덱스까지 생성
    python setup_env.py --force  # Python·Node 의존성을 다시 설치

표준 라이브러리만 사용하므로 가상환경 없이 시스템 Python으로 실행한다.
설치가 끝나면 `python a11y.py ...`로 CLI를 실행한다(가상환경 활성화 불필요).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 11)
MIN_NODE = 20
REQUIRED_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
STAMP_NAME = ".a11y-setup"  # inside .venv: fingerprint of the installed requirements


# ── Helpers (unit-tested in tests/test_setup_env.py) ────────


def venv_python(root: Path = ROOT, windows: bool | None = None) -> Path:
    """Path of the virtual environment's Python (differs between Windows and macOS/Linux)."""
    windows = os.name == "nt" if windows is None else windows
    return root / ".venv" / ("Scripts/python.exe" if windows else "bin/python")


def deps_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for name in ("requirements.txt", "pyproject.toml"):
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def needs_python_install(root: Path = ROOT, windows: bool | None = None) -> bool:
    stamp = root / ".venv" / STAMP_NAME
    if not venv_python(root, windows).exists() or not stamp.exists():
        return True
    return stamp.read_text(encoding="utf-8").strip() != deps_fingerprint(root)


def parse_env(path: Path) -> dict[str, str]:
    """Minimal .env reader: KEY=VALUE lines, `#` comments, optional quotes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def missing_env(values: dict[str, str]) -> list[str]:
    return [k for k in REQUIRED_ENV if not values.get(k)]


def node_major(version: str) -> int | None:
    """'v26.1.0' -> 26."""
    try:
        return int(version.strip().lstrip("v").split(".")[0])
    except ValueError:
        return None


def index_exists(root: Path = ROOT) -> bool:
    return (root / "data" / "chroma" / "chroma.sqlite3").exists()


# ── Steps ────────────────────────────────────────────────────


class SetupError(Exception):
    pass


def step(title: str) -> None:
    print(f"\n▶ {title}")


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("  $ " + " ".join(str(c) for c in cmd))
    result = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if result.returncode != 0:
        raise SetupError(f"명령이 실패했습니다 (종료 코드 {result.returncode}). 위 출력을 확인하세요.")


def check_python() -> None:
    step("Python 확인")
    if sys.version_info < MIN_PYTHON:
        raise SetupError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다(현재 {sys.version.split()[0]}). "
            "https://www.python.org/downloads/ 에서 설치하세요."
        )
    print(f"  Python {sys.version.split()[0]} ✓")


def check_node() -> str:
    step("Node.js 확인 (정적 분석기 실행용)")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise SetupError(
            f"Node.js {MIN_NODE} 이상이 필요합니다. https://nodejs.org/ 에서 LTS를 설치한 뒤 "
            "새 터미널에서 다시 실행하세요."
        )
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    major = node_major(version)
    if major is None or major < MIN_NODE:
        raise SetupError(f"Node.js {MIN_NODE} 이상이 필요합니다(현재 {version or '알 수 없음'}).")
    print(f"  Node.js {version} ✓")
    return npm


def install_python(force: bool) -> None:
    step("Python 가상환경과 의존성 (.venv)")
    py = venv_python()
    if not py.exists():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    if force or needs_python_install():
        run([py, "-m", "pip", "install", "-r", "requirements.txt", "-e", "."])
        (ROOT / ".venv" / STAMP_NAME).write_text(deps_fingerprint(), encoding="utf-8")
    else:
        print("  이미 설치되어 있습니다(requirements.txt 변경 없음). 건너뜁니다.")


def install_node(npm: str, force: bool) -> None:
    step("정적 분석기 의존성 (analyzer-js)")
    analyzer = ROOT / "analyzer-js"
    if force or not (analyzer / "node_modules").exists():
        run([npm, "install"], cwd=analyzer)
    else:
        print("  이미 설치되어 있습니다. 건너뜁니다.")


def prepare_env() -> bool:
    """Return True when the required AWS keys are filled in."""
    step("환경변수 (.env)")
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists():
        shutil.copyfile(example, env)
        print("  .env.example을 복사해 .env를 만들었습니다.")
    missing = missing_env(parse_env(env))
    if missing:
        print(f"  .env에 다음 값을 채워야 합니다: {', '.join(missing)}")
        print(f"  파일 위치: {env}")
        return False
    print("  AWS 자격 증명이 입력되어 있습니다 ✓ (값은 출력하지 않습니다)")
    return True


def build_index(assume_yes: bool) -> bool:
    step("검색 인덱스 (data/chroma)")
    if index_exists():
        print("  이미 만들어져 있습니다. 건너뜁니다.")
        return True
    print("  WCAG·APG 문서를 Bedrock 임베딩으로 인덱싱합니다(약 2분, 임베딩 비용은 매우 작음).")
    if not assume_yes:
        no_input = "  입력을 받을 수 없는 환경이라 건너뜁니다. `python setup_env.py --yes`로 실행하세요."
        if not sys.stdin.isatty():
            print(no_input)
            return False
        try:
            answer = input("  지금 만들까요? [Y/n] ").strip().lower()
        except EOFError:  # isatty() can be True without a usable stdin (some IDE terminals)
            print("\n" + no_input)
            return False
        if answer not in ("", "y", "yes"):
            print("  건너뜁니다. 나중에 `python setup_env.py`를 다시 실행하세요.")
            return False
    run([venv_python(), "-m", "a11y_investigator.rag.ingest"])
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A11y Investigator 설치")
    parser.add_argument("--yes", "-y", action="store_true", help="질문 없이 검색 인덱스까지 생성")
    parser.add_argument("--force", action="store_true", help="Python·Node 의존성을 다시 설치")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            # line buffering keeps our messages in order with the pip / npm output
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    try:
        check_python()
        npm = check_node()
        install_python(args.force)
        install_node(npm, args.force)
        ready = prepare_env() and build_index(args.yes)
    except SetupError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n중단했습니다. 다시 실행하면 끝난 단계는 건너뜁니다.", file=sys.stderr)
        return 130

    if not ready:
        print("\n남은 단계가 있습니다. 위 안내를 처리한 뒤 `python setup_env.py`를 다시 실행하세요.")
        return 0
    print("\n✓ 설치가 끝났습니다. 다음 명령으로 실행해 보세요 (Bedrock 호출, 1회 약 $0.06):")
    print("  python a11y.py analyze --file examples/save_button.jsx --project demo-ds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
