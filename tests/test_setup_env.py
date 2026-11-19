"""T21: setup script helpers and the launcher (offline, no installs)."""
from __future__ import annotations

import subprocess
import sys

import setup_env
from setup_env import (
    STAMP_NAME,
    deps_fingerprint,
    missing_env,
    needs_python_install,
    node_major,
    parse_env,
    venv_python,
)


def test_venv_python_per_os(tmp_path) -> None:
    assert venv_python(tmp_path, windows=True) == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert venv_python(tmp_path, windows=False) == tmp_path / ".venv" / "bin" / "python"


def test_needs_install_until_stamp_matches(tmp_path) -> None:
    (tmp_path / "requirements.txt").write_text("typer==0.29.1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert needs_python_install(tmp_path, windows=False)  # no venv yet

    py = venv_python(tmp_path, windows=False)
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    assert needs_python_install(tmp_path, windows=False)  # venv but no stamp

    (tmp_path / ".venv" / STAMP_NAME).write_text(deps_fingerprint(tmp_path), encoding="utf-8")
    assert not needs_python_install(tmp_path, windows=False)

    (tmp_path / "requirements.txt").write_text("typer==0.30.0\n", encoding="utf-8")
    assert needs_python_install(tmp_path, windows=False)  # requirements changed


def test_parse_env_and_missing_keys(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "AWS_ACCESS_KEY_ID=AKIA123\n"
        "AWS_SECRET_ACCESS_KEY=\n"
        'AWS_DEFAULT_REGION="us-west-1"          # chat model region\n'
        "# EMBEDDING_REGION=us-east-1\n",
        encoding="utf-8",
    )
    values = parse_env(env)
    assert values["AWS_DEFAULT_REGION"] == "us-west-1"
    assert "EMBEDDING_REGION" not in values
    assert missing_env(values) == ["AWS_SECRET_ACCESS_KEY"]
    assert parse_env(tmp_path / "nope.env") == {}


def test_example_env_is_incomplete_by_design() -> None:
    """A freshly copied .env.example must be reported as missing keys."""
    assert missing_env(parse_env(setup_env.ROOT / ".env.example")) == list(setup_env.REQUIRED_ENV)


def test_node_major() -> None:
    assert node_major("v26.1.0") == 26
    assert node_major("20.11.1\n") == 20
    assert node_major("") is None


def test_launcher_dev_commands() -> None:
    from a11y import build_command

    assert build_command(["test", "--no-node"]) == (["-m", "pytest", "--no-node"], str(setup_env.ROOT))
    assert build_command(["eval", "--case", "button"]) == (["-m", "evals.evaluate", "--case", "button"], str(setup_env.ROOT))
    assert build_command(["analyze", "--file", "x.jsx"]) == (["-m", "a11y_investigator", "analyze", "--file", "x.jsx"], None)


def test_launcher_runs_cli_from_any_cwd(tmp_path) -> None:
    """`python a11y.py` works without an activated venv and from another directory."""
    launcher = setup_env.ROOT / "a11y.py"
    result = subprocess.run(
        [sys.executable, str(launcher), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "analyze" in result.stdout and "policies" in result.stdout
