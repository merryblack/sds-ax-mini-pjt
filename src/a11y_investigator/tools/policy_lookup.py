"""Project policies and project.yaml loading (SERVICE_MVP.md 6.2).

Layout:
    knowledge/project-policies/<project_id>/project.yaml   # target_level, component_mapping
    knowledge/project-policies/<project_id>/*.md           # one policy rule per file (YAML frontmatter)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from a11y_investigator.config import settings
from a11y_investigator.rag.metadata import Chunk, ChunkMetadata
from a11y_investigator.schemas.analyzer import TargetLevel

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
COMPONENTS = {"button", "dialog", "tabs", "combobox"}


class PolicyError(ValueError):
    pass


class ProjectConfig(BaseModel):
    project_id: str
    name: str = ""
    target_level: TargetLevel = "AA"
    component_mapping: dict[str, str] = Field(default_factory=dict)


class Policy(BaseModel):
    policy_id: str
    project_id: str
    title: str
    applies_to: list[str] = Field(default_factory=list)
    related_wcag: list[str] = Field(default_factory=list)
    body: str
    path: str  # repo-relative

    @field_validator("applies_to")
    @classmethod
    def _known_components(cls, values: list[str]) -> list[str]:
        unknown = set(values) - COMPONENTS
        if unknown:
            raise ValueError(f"unknown components in applies_to: {sorted(unknown)}")
        return values

    def to_text(self) -> str:
        return f"[프로젝트 정책 {self.policy_id}] {self.title}\n{self.body}"


def _project_dir(project_id: str, root: Path | None = None) -> Path:
    return (root or settings.policies_dir) / project_id


def list_projects(root: Path | None = None) -> list[str]:
    root = root or settings.policies_dir
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "project.yaml").is_file())


def load_project(project_id: str, root: Path | None = None) -> ProjectConfig:
    path = _project_dir(project_id, root) / "project.yaml"
    if not path.is_file():
        raise PolicyError(f"알 수 없는 프로젝트입니다: {project_id}")
    config = ProjectConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    if config.project_id != project_id:
        raise PolicyError(f"{path}: project_id '{config.project_id}' does not match folder '{project_id}'")
    return config


def parse_policy(path: Path, project_id: str) -> Policy:
    match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if not match:
        raise PolicyError(f"{path}: missing YAML frontmatter")
    front = yaml.safe_load(match.group(1)) or {}
    if front.get("project_id") != project_id:
        raise PolicyError(f"{path}: project_id must be '{project_id}'")
    try:
        rel = path.relative_to(settings.project_root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return Policy(**front, body=match.group(2).strip(), path=rel)


def load_policies(project_id: str, root: Path | None = None) -> list[Policy]:
    load_project(project_id, root)  # validates the project exists
    policies = [parse_policy(p, project_id) for p in sorted(_project_dir(project_id, root).glob("*.md"))]
    ids = [p.policy_id for p in policies]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise PolicyError(f"duplicate policy_id in {project_id}: {sorted(duplicates)}")
    return policies


def get_project_policy(project_id: str, policy_id: str, root: Path | None = None) -> Policy:
    """Exact lookup of one policy rule."""
    for policy in load_policies(project_id, root):
        if policy.policy_id == policy_id:
            return policy
    raise PolicyError(f"{project_id}에 정책 {policy_id}가 없습니다.")


def check_project(
    project_id: str, root: Path | None = None, known_sc: set[str] | frozenset[str] | None = None
) -> tuple[list[Policy], list[str]]:
    """Validate a project folder and collect ALL problems (Korean), not just the first.

    Used by `a11y-investigator policies check`. `known_sc` is the set of indexed WCAG SC.
    """
    problems: list[str] = []
    folder = _project_dir(project_id, root)
    if not folder.is_dir():
        return [], [f"프로젝트 폴더가 없습니다: {folder}"]
    try:
        config = load_project(project_id, root)
        for component, element in config.component_mapping.items():
            if not str(element).strip():
                problems.append(f"project.yaml: component_mapping['{component}']의 값이 비어 있습니다.")
    except Exception as e:  # missing file, bad YAML, invalid field, id mismatch
        problems.append(f"project.yaml: {e}")

    policies: list[Policy] = []
    files = sorted(folder.glob("*.md"))
    if not files:
        problems.append("정책 파일(*.md)이 없습니다.")
    for path in files:
        try:
            policy = parse_policy(path, project_id)
        except Exception as e:
            problems.append(f"{path.name}: {e}")
            continue
        policies.append(policy)
        if known_sc is not None:
            unknown = [sc for sc in policy.related_wcag if sc not in known_sc]
            if unknown:
                problems.append(f"{path.name}: 인덱스에 없는 WCAG 기준 {unknown}")

    seen: dict[str, str] = {}
    for policy in policies:
        name = Path(policy.path).name
        if policy.policy_id in seen:
            problems.append(f"{name}: policy_id '{policy.policy_id}'가 {seen[policy.policy_id]}와 중복됩니다.")
        seen.setdefault(policy.policy_id, name)
    return policies, problems


def policy_chunks(root: Path | None = None) -> list[Chunk]:
    """One chunk per policy rule, for every project."""
    chunks = []
    for project_id in list_projects(root):
        for policy in load_policies(project_id, root):
            meta = ChunkMetadata(
                document_id=policy.policy_id,
                source_type="project_policy",
                source_name=f"Project policy ({project_id})",
                title=policy.title,
                component=",".join(policy.applies_to),
                wcag_sc=policy.related_wcag,
                project_id=project_id,
                source_url=policy.path,
            )
            chunks.append(Chunk(text=policy.to_text(), metadata=meta))
    return chunks
