"""T22: project policy template and `policies init` (SERVICE_MVP.md 6.2). Offline."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from a11y_investigator.cli import app
from a11y_investigator.middleware.safety import indexed_sc
from a11y_investigator.tools.policy_lookup import (
    TEMPLATE_DIR,
    PolicyError,
    check_project,
    init_project,
    list_projects,
    load_project,
)

runner = CliRunner()


def test_template_lives_in_package() -> None:
    assert (TEMPLATE_DIR / "project.yaml").is_file()
    assert (TEMPLATE_DIR / "policy-example.md").is_file()


def test_init_creates_a_valid_project(tmp_path) -> None:
    """Guards the template itself: whatever init produces must pass `policies check`."""
    created = init_project("my-team-ds", tmp_path)
    assert sorted(p.name for p in created) == ["btn-001.md", "project.yaml"]
    policies, problems = check_project("my-team-ds", tmp_path, known_sc=indexed_sc())
    assert problems == []
    assert [p.policy_id for p in policies] == ["my-team-ds-btn-001"]
    assert load_project("my-team-ds", tmp_path).project_id == "my-team-ds"
    assert list_projects(tmp_path) == ["my-team-ds"]


def test_init_never_overwrites(tmp_path) -> None:
    init_project("team-a", tmp_path)
    (tmp_path / "team-a" / "btn-001.md").write_text("edited", encoding="utf-8")
    with pytest.raises(PolicyError, match="덮어쓰지 않습니다"):
        init_project("team-a", tmp_path)
    assert (tmp_path / "team-a" / "btn-001.md").read_text(encoding="utf-8") == "edited"


@pytest.mark.parametrize("bad", ["My-Project", "my_project", "-lead", "a/b", "..", ""])
def test_init_rejects_bad_ids(tmp_path, bad) -> None:
    with pytest.raises(PolicyError, match="프로젝트 ID"):
        init_project(bad, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_cli_init_then_check(tmp_path) -> None:
    result = runner.invoke(app, ["policies", "init", "web-ds", "--policies-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "✓ web-ds: 정책 1개, 문제 없음" in result.output
    assert "python a11y.py policies check web-ds" in result.output

    again = runner.invoke(app, ["policies", "init", "web-ds", "--policies-dir", str(tmp_path)])
    assert again.exit_code == 2
