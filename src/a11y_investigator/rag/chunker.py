"""Document-type-aware chunking for official sources (SPEC_MVP.md 6.4).

| Source        | Unit                                                         |
|---------------|--------------------------------------------------------------|
| WCAG          | one chunk per success criterion (from wcag.json)             |
| Understanding | brief / intent / benefits / examples sections                |
| Techniques    | description and examples sections                            |
| APG           | about / keyboard interaction / roles-states-properties       |

Sections longer than CHUNK_SIZE are split with overlap; split parts get a
`-p2`, `-p3`, ... suffix on their document_id.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

from a11y_investigator.config import settings
from a11y_investigator.rag.metadata import Chunk, ChunkMetadata

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

UNDERSTANDING_SECTIONS = ("brief", "intent", "benefits", "examples")
TECHNIQUE_SECTIONS = ("description", "examples")
APG_SECTIONS = {"about": "about", "keyboard_interaction": "keyboard", "roles_states_properties": "roles"}
APG_TITLES = {"button": "Button", "dialog": "Dialog (Modal)", "tabs": "Tabs", "combobox": "Combobox"}

_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


BLOCK_TAGS = (
    "p", "li", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "div",
    "tr", "section", "blockquote", "figcaption", "table", "ul", "ol", "dl",
)


def clean_text(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(node) -> str:
    """Text with line breaks only at block elements (inline links/code stay in the sentence)."""
    node = BeautifulSoup(str(node), "html.parser")  # work on a copy
    for br in node.find_all("br"):
        br.replace_with("\n")
    for tag in node.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = node.get_text()
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    # join lines that were only wrapped in the source HTML (no block boundary)
    return clean_text(text)


def _split(header: str, body: str, meta: ChunkMetadata) -> list[Chunk]:
    """Prefix each piece with a header so it embeds with its context."""
    pieces = _splitter.split_text(body) if len(body) > CHUNK_SIZE else [body]
    chunks = []
    for i, piece in enumerate(pieces, start=1):
        doc_id = meta.document_id if i == 1 else f"{meta.document_id}-p{i}"
        chunks.append(
            Chunk(text=f"{header}\n{piece}", metadata=meta.model_copy(update={"document_id": doc_id}))
        )
    return chunks


def load_manifest(path: Path | None = None) -> dict:
    path = path or settings.manifests_dir / "sources.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sc_index(official_dir: Path) -> dict[str, dict]:
    wcag = json.loads((official_dir / "wcag" / "wcag.json").read_text(encoding="utf-8"))
    return {
        sc["num"]: sc
        for p in wcag["principles"]
        for g in p["guidelines"]
        for sc in g["successcriteria"]
    }


def wcag_chunks(manifest: dict, official_dir: Path) -> list[Chunk]:
    index = _sc_index(official_dir)
    chunks = []
    for entry in manifest["wcag"]["success_criteria"]:
        sc = index[entry["sc"]]
        text = html_to_text(BeautifulSoup(sc["content"], "html.parser"))
        techniques = [
            t for t in manifest["wcag_repo"]["techniques"] if entry["sc"] in t.get("sc", [])
        ]
        if techniques:
            text += "\nSufficient techniques: " + "; ".join(f"{t['id']} {t['title']}" for t in techniques)
        meta = ChunkMetadata(
            document_id=f"wcag-{sc['num']}",
            source_type="wcag",
            source_name="WCAG 2.2",
            title=f"{sc['num']} {sc['handle']}",
            section="Success Criterion",
            wcag_sc=[sc["num"]],
            wcag_level=sc["level"],
            source_url=f"https://www.w3.org/TR/WCAG22/#{sc['id']}",
        )
        header = f"[WCAG 2.2 Success Criterion {sc['num']} {sc['handle']} (Level {sc['level']})]"
        chunks += _split(header, text, meta)
    return chunks


def understanding_chunks(manifest: dict, official_dir: Path) -> list[Chunk]:
    levels = {e["sc"]: e["level"] for e in manifest["wcag"]["success_criteria"]}
    chunks = []
    for entry in manifest["wcag_repo"]["understanding"]:
        soup = BeautifulSoup(
            (official_dir / "understanding" / f"{entry['id']}.html").read_text(encoding="utf-8"),
            "html.parser",
        )
        handle = (soup.title.string or entry["id"]).replace("Understanding", "").strip()
        for section_id in UNDERSTANDING_SECTIONS:
            section = soup.find("section", id=section_id)
            if section is None:
                continue
            heading = section.find(["h2", "h3"])
            if heading:
                heading.extract()
            body = html_to_text(section)
            if not body:
                continue
            meta = ChunkMetadata(
                document_id=f"understanding-{entry['sc']}-{section_id}",
                source_type="understanding",
                source_name="Understanding WCAG 2.2",
                title=f"Understanding {entry['sc']} {handle}",
                section=section_id,
                wcag_sc=[entry["sc"]],
                wcag_level=levels.get(entry["sc"], ""),
                source_url=f"https://www.w3.org/WAI/WCAG22/Understanding/{entry['id']}.html#{section_id}",
            )
            header = f"[Understanding WCAG 2.2 — {entry['sc']} {handle} — {section_id}]"
            chunks += _split(header, body, meta)
    return chunks


def technique_chunks(manifest: dict, official_dir: Path) -> list[Chunk]:
    chunks = []
    for tech in manifest["wcag_repo"]["techniques"]:
        soup = BeautifulSoup(
            (official_dir / "techniques" / f"{tech['id']}.html").read_text(encoding="utf-8"),
            "html.parser",
        )
        title = soup.title.string.strip() if soup.title and soup.title.string else tech["title"]
        for section_id in TECHNIQUE_SECTIONS:
            section = soup.find("section", id=section_id)
            if section is None:
                continue
            heading = section.find("h2")
            if heading:
                heading.extract()
            body = html_to_text(section)
            if not body:
                continue
            meta = ChunkMetadata(
                document_id=f"technique-{tech['id']}-{section_id}",
                source_type="technique",
                source_name="Techniques for WCAG 2.2",
                title=f"{tech['id']}: {title}",
                section=section_id,
                wcag_sc=list(tech.get("sc", [])),
                source_url=(
                    f"https://www.w3.org/WAI/WCAG22/Techniques/{tech['technology']}/{tech['id']}#{section_id}"
                ),
            )
            header = f"[WCAG Technique {tech['id']}: {title} — {section_id}]"
            chunks += _split(header, body, meta)
    return chunks


def apg_chunks(manifest: dict, official_dir: Path) -> list[Chunk]:
    chunks = []
    for entry in manifest["apg_repo"]["patterns"]:
        pattern = entry["pattern"]
        soup = BeautifulSoup(
            (official_dir / "apg" / f"{pattern}.html").read_text(encoding="utf-8"), "html.parser"
        )
        for section_id, short in APG_SECTIONS.items():
            section = soup.find("section", id=section_id)
            if section is None:
                continue
            heading = section.find("h2")
            heading_text = heading.get_text(" ", strip=True) if heading else short
            if heading:
                heading.extract()
            body = html_to_text(section)
            if not body:
                continue
            meta = ChunkMetadata(
                document_id=f"apg-{pattern}-{short}",
                source_type="apg",
                source_name="WAI-ARIA APG",
                title=f"{APG_TITLES[pattern]} Pattern",
                section=heading_text,
                component=pattern,
                source_url=f"https://www.w3.org/WAI/ARIA/apg/patterns/{entry['dir']}/#{section_id}",
            )
            header = f"[WAI-ARIA APG — {APG_TITLES[pattern]} Pattern — {heading_text}]"
            chunks += _split(header, body, meta)
    return chunks


def official_chunks(official_dir: Path | None = None, manifest: dict | None = None) -> list[Chunk]:
    official_dir = official_dir or settings.official_dir
    manifest = manifest or load_manifest()
    chunks = (
        wcag_chunks(manifest, official_dir)
        + understanding_chunks(manifest, official_dir)
        + technique_chunks(manifest, official_dir)
        + apg_chunks(manifest, official_dir)
    )
    ids = [c.id for c in chunks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate chunk ids: {sorted(duplicates)}")
    return chunks
