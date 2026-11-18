"""Chroma metadata normalization (SERVICE_MVP.md 6.4).

Chroma metadata values must be scalars (str / int / float / bool) and cannot be
None. Lists are stored as comma-separated strings and None as "".
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from a11y_investigator.config import settings

SourceType = Literal["wcag", "understanding", "technique", "apg", "project_policy"]


class ChunkMetadata(BaseModel):
    document_id: str
    source_type: SourceType
    source_name: str
    title: str
    section: str = ""
    component: str = ""  # APG pattern / policy target: button | dialog | tabs | combobox
    wcag_sc: list[str] = Field(default_factory=list)
    wcag_level: str = ""  # A | AA | AAA (SC and Understanding only)
    project_id: str = ""
    source_url: str = ""
    index_version: str = settings.index_version

    def to_chroma(self) -> dict[str, str]:
        data = self.model_dump()
        data["wcag_sc"] = ",".join(self.wcag_sc)
        return {k: ("" if v is None else str(v)) for k, v in data.items()}


def from_chroma(metadata: dict) -> ChunkMetadata:
    data = dict(metadata)
    raw = data.get("wcag_sc", "")
    data["wcag_sc"] = [s for s in str(raw).split(",") if s]
    return ChunkMetadata.model_validate(data)


class Chunk(BaseModel):
    """One indexable unit. `metadata.document_id` is also the Chroma record id."""

    text: str
    metadata: ChunkMetadata

    @property
    def id(self) -> str:
        return self.metadata.document_id
