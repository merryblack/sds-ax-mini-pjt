"""T02 smoke test: package imports and settings resolve."""
from a11y_investigator.config import settings


def test_settings_defaults() -> None:
    assert settings.max_code_lines == 300
    assert settings.max_fix_retries == 2
    assert settings.chat_model_id
    assert settings.embedding_model_id


def test_paths_point_into_project() -> None:
    assert (settings.project_root / "SPEC_MVP.md").exists()
    assert settings.knowledge_dir.is_dir()
