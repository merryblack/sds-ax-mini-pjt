"""Download official sources into knowledge/official/ (SERVICE_MVP.md 6.1).

Scope (MVP):
- WCAG 2.2 success criteria: every SC in the rule mapping + component-related extras.
  Text comes from the official W3C JSON (https://www.w3.org/WAI/WCAG22/wcag.json).
- Understanding documents for those SC (GitHub w3c/wcag, pinned commit).
- Sufficient techniques for those SC, ARIA / client-side script / HTML only (w3c/wcag).
- APG patterns: Button, Dialog (Modal), Tabs, Combobox (GitHub w3c/aria-practices).

Writes knowledge/manifests/sources.yaml with URLs and commit hashes.

Usage:
    python -m a11y_investigator.rag.fetch
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

import yaml

from a11y_investigator.config import settings
from a11y_investigator.tools.rule_mapping import all_mapped_sc

USER_AGENT = "a11y-investigator-docs-fetch"
WCAG_JSON_URL = "https://www.w3.org/WAI/WCAG22/wcag.json"
WCAG_REPO = "w3c/wcag"
APG_REPO = "w3c/aria-practices"

# SC not produced by any static rule but central to the four MVP components
# (focus management, keyboard traps, status messages, contrast for manual review).
EXTRA_SC = {"1.4.3", "1.4.11", "2.1.2", "2.4.7", "2.4.11", "2.5.3", "4.1.3"}
TECHNIQUE_TECHNOLOGIES = {"aria", "client-side-script", "html"}
APG_PATTERNS = {
    "button": "button/button-pattern.html",
    "dialog": "dialog-modal/dialog-modal-pattern.html",
    "tabs": "tabs/tabs-pattern.html",
    "combobox": "combobox/combobox-pattern.html",
}

OFFICIAL = settings.official_dir
SOURCES_YAML = settings.manifests_dir / "sources.yaml"


def _get(url: str, retries: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def head_commit(repo: str) -> str:
    return json.loads(_get(f"https://api.github.com/repos/{repo}/commits/main"))["sha"]


def target_sc() -> list[str]:
    return sorted(all_mapped_sc() | EXTRA_SC, key=lambda s: [int(x) for x in s.split(".")])


def iter_sc(wcag: dict):
    for principle in wcag["principles"]:
        for guideline in principle["guidelines"]:
            yield from guideline["successcriteria"]


def sufficient_techniques(sc: dict) -> list[dict]:
    """Flatten sufficient techniques (including nested `using` / `and` groups)."""
    found: list[dict] = []

    def walk(items: list) -> None:
        for item in items or []:
            if item.get("id") and item.get("technology"):
                found.append({"id": item["id"], "technology": item["technology"], "title": item.get("title", "")})
            walk(item.get("using", []))
            walk(item.get("and", []))

    techniques = sc.get("techniques") or {}
    sufficient = techniques.get("sufficient", [])
    # some SC group sufficient techniques by situation: [{"title": ..., "techniques": [...]}]
    for group in sufficient:
        walk([group])
        walk(group.get("techniques", []))
    return found


def understanding_folder(sc: dict) -> str:
    first_version = sorted(sc.get("versions", ["2.0"]))[0]
    return first_version.replace(".", "")  # "2.1" -> "21"


def fetch(out_dir: Path = OFFICIAL) -> dict:
    wcag_commit = head_commit(WCAG_REPO)
    apg_commit = head_commit(APG_REPO)
    raw_wcag = f"https://raw.githubusercontent.com/{WCAG_REPO}/{wcag_commit}"
    raw_apg = f"https://raw.githubusercontent.com/{APG_REPO}/{apg_commit}"

    (out_dir / "wcag").mkdir(parents=True, exist_ok=True)
    wcag_bytes = _get(WCAG_JSON_URL)
    (out_dir / "wcag" / "wcag.json").write_bytes(wcag_bytes)
    wcag = json.loads(wcag_bytes)

    wanted = set(target_sc())
    selected = [sc for sc in iter_sc(wcag) if sc["num"] in wanted]
    missing = wanted - {sc["num"] for sc in selected}
    if missing:
        raise RuntimeError(f"SC not found in wcag.json: {sorted(missing)}")

    understanding: list[dict] = []
    techniques: dict[str, dict] = {}
    for sc in selected:
        rel = f"understanding/{understanding_folder(sc)}/{sc['id']}.html"
        dest = out_dir / "understanding" / f"{sc['id']}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_get(f"{raw_wcag}/{rel}"))
        understanding.append({"sc": sc["num"], "id": sc["id"], "path": rel})

        for tech in sufficient_techniques(sc):
            if tech["technology"] not in TECHNIQUE_TECHNOLOGIES:
                continue
            entry = techniques.setdefault(tech["id"], {**tech, "sc": []})
            if sc["num"] not in entry["sc"]:
                entry["sc"].append(sc["num"])

    for tech in techniques.values():
        rel = f"techniques/{tech['technology']}/{tech['id']}.html"
        dest = out_dir / "techniques" / f"{tech['id']}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_get(f"{raw_wcag}/{rel}"))
        tech["path"] = rel

    apg: list[dict] = []
    for pattern, rel_in_patterns in APG_PATTERNS.items():
        rel = f"content/patterns/{rel_in_patterns}"
        dest = out_dir / "apg" / f"{pattern}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_get(f"{raw_apg}/{rel}"))
        apg.append({"pattern": pattern, "path": rel, "dir": rel_in_patterns.split("/")[0]})

    manifest = {
        "fetched_on": date.today().isoformat(),
        "license": "W3C Software and Document License — https://www.w3.org/copyright/software-license/",
        "wcag": {
            "version": "2.2",
            "url": WCAG_JSON_URL,
            "success_criteria": [{"sc": sc["num"], "id": sc["id"], "level": sc["level"]} for sc in selected],
        },
        "wcag_repo": {
            "repo": WCAG_REPO,
            "commit": wcag_commit,
            "understanding": understanding,
            "techniques": sorted(techniques.values(), key=lambda t: t["id"]),
        },
        "apg_repo": {"repo": APG_REPO, "commit": apg_commit, "patterns": apg},
    }
    SOURCES_YAML.write_text(
        "# Generated by `python -m a11y_investigator.rag.fetch`. Do not edit by hand.\n"
        + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    m = fetch()
    print(
        f"SC {len(m['wcag']['success_criteria'])}, "
        f"understanding {len(m['wcag_repo']['understanding'])}, "
        f"techniques {len(m['wcag_repo']['techniques'])}, "
        f"APG {len(m['apg_repo']['patterns'])} -> {OFFICIAL}"
    )
