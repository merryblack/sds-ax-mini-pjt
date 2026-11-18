"""T09: example project policies (SERVICE_MVP.md 6.2, Scenario C)."""
from __future__ import annotations

import pytest

from a11y_investigator.config import settings
from a11y_investigator.tools.policy_lookup import (
    PolicyError,
    get_project_policy,
    list_projects,
    load_policies,
    load_project,
    policy_chunks,
)
from a11y_investigator.tools.static_analysis import StaticAnalysisError, analyze_code, find_node


def write_project(root, project_id="p1", policy_front=None):
    d = root / project_id
    d.mkdir(parents=True)
    (d / "project.yaml").write_text(f"project_id: {project_id}\n", encoding="utf-8")
    front = policy_front or f"policy_id: {project_id}-001\nproject_id: {project_id}\ntitle: t"
    (d / "a.md").write_text(f"---\n{front}\n---\nbody\n", encoding="utf-8")
    return d


# ── Loading ─────────────────────────────────────────────────


def test_demo_project_config() -> None:
    assert "demo-ds" in list_projects()
    config = load_project("demo-ds")
    assert config.target_level == "AA"
    assert config.component_mapping["Button"] == "button"
    assert config.component_mapping["Link"] == "a"


def test_demo_policies() -> None:
    policies = load_policies("demo-ds")
    ids = [p.policy_id for p in policies]
    assert len(ids) == 5 and len(set(ids)) == 5
    assert all(p.project_id == "demo-ds" and p.body for p in policies)
    conflict = get_project_policy("demo-ds", "demo-ds-focus-001")
    assert conflict.related_wcag == ["2.4.7"]


def test_unknown_project_and_policy() -> None:
    with pytest.raises(PolicyError):
        load_project("no-such-project")
    with pytest.raises(PolicyError):
        get_project_policy("demo-ds", "demo-ds-xxx")


def test_project_id_mismatch_rejected(tmp_path) -> None:
    write_project(tmp_path, "p1", "policy_id: x\nproject_id: other\ntitle: t")
    with pytest.raises(PolicyError, match="project_id"):
        load_policies("p1", root=tmp_path)


def test_unknown_component_rejected(tmp_path) -> None:
    write_project(tmp_path, "p1", "policy_id: x\nproject_id: p1\ntitle: t\napplies_to: [carousel]")
    with pytest.raises(ValueError):
        load_policies("p1", root=tmp_path)


def test_policy_chunks_metadata() -> None:
    chunks = policy_chunks()
    assert len(chunks) == 5
    btn = next(c for c in chunks if c.id == "demo-ds-btn-001")
    meta = btn.metadata.to_chroma()
    assert meta["source_type"] == "project_policy"
    assert meta["project_id"] == "demo-ds"
    assert meta["component"] == "button"
    assert meta["wcag_sc"] == "2.1.1,4.1.2"
    assert btn.text.startswith("[프로젝트 정책 demo-ds-btn-001]")


# ── component_mapping injection into jsx-a11y ───────────────

try:
    find_node()
    HAS_NODE = True
except StaticAnalysisError:
    HAS_NODE = False


@pytest.mark.skipif(not HAS_NODE, reason="Node.js not installed")
def test_component_mapping_makes_jsx_a11y_treat_button_as_button() -> None:
    """With the mapping, <Button> is a native button, so giving it a non-interactive role is flagged."""
    code = 'export const A = () => <Button role="presentation" onClick={() => 1}>저장</Button>;'
    mapping = load_project("demo-ds").component_mapping
    without = analyze_code(code, "jsx")
    with_map = analyze_code(code, "jsx", mapping)
    assert without.findings == []
    assert [f.rule_id for f in with_map.findings] == [
        "jsx-a11y/no-interactive-element-to-noninteractive-role"
    ]
    assert with_map.findings[0].element == "Button"


# ── Index (local Chroma, no embedding calls) ────────────────

needs_index = pytest.mark.skipif(
    not (settings.chroma_dir / "chroma.sqlite3").exists(), reason="run rag.ingest first"
)


@needs_index
def test_policy_index_filtered_by_project() -> None:
    from a11y_investigator.rag.store import get_collection

    store = get_collection(settings.policy_collection)
    demo = store.get(where={"project_id": "demo-ds"})
    other = store.get(where={"project_id": "other-project"})
    assert len(demo["ids"]) == 5
    assert other["ids"] == []


@needs_index
@pytest.mark.llm
def test_policy_semantic_search_with_project_filter() -> None:
    from a11y_investigator.rag.store import get_collection

    store = get_collection(settings.policy_collection)
    docs = store.similarity_search("클릭 가능한 div 버튼", k=2, filter={"project_id": "demo-ds"})
    assert docs[0].metadata["document_id"] == "demo-ds-btn-001"
    assert store.similarity_search("버튼", k=2, filter={"project_id": "other-project"}) == []
