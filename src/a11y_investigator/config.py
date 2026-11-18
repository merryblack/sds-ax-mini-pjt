"""Central settings: models, paths, and limits (SERVICE_MVP.md 10장, 14장).

Values come from environment variables (loaded from the project-root `.env`),
falling back to the defaults decided in docs/decisions.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


@dataclass(frozen=True)
class Settings:
    # ── Models (AWS Bedrock, D1·D2) ─────────────────────────
    aws_region: str = field(default_factory=lambda: _env("AWS_DEFAULT_REGION", "us-east-1"))
    chat_model_id: str = field(
        default_factory=lambda: _env("CHAT_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    )
    chat_model_id_light: str = field(
        default_factory=lambda: _env(
            "CHAT_MODEL_ID_LIGHT", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
    )
    embedding_model_id: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
    )
    temperature: float = 0.0

    # ── Paths ───────────────────────────────────────────────
    project_root: Path = PROJECT_ROOT
    knowledge_dir: Path = PROJECT_ROOT / "knowledge"
    official_dir: Path = PROJECT_ROOT / "knowledge" / "official"
    policies_dir: Path = PROJECT_ROOT / "knowledge" / "project-policies"
    manifests_dir: Path = PROJECT_ROOT / "knowledge" / "manifests"
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"
    analyzer_dir: Path = PROJECT_ROOT / "analyzer-js"

    # ── Index ───────────────────────────────────────────────
    index_version: str = "index-v1"
    official_collection: str = "official"
    policy_collection: str = "project_policies"

    # ── Input limits (2.3) ──────────────────────────────────
    max_code_lines: int = 300
    max_code_tokens: int = 8000

    # ── Analyzer (5.1) ──────────────────────────────────────
    analyzer_timeout_sec: int = 20

    # ── Fix loop (5.3) ──────────────────────────────────────
    max_fix_retries: int = 2  # total attempts = 1 + retries

    # ── Retrieval caps (6.5) ────────────────────────────────
    max_official_docs: int = 6
    max_policy_docs: int = 4

    # ── Graph (4.1) ─────────────────────────────────────────
    recursion_limit: int = 25

    # ── Defaults (2.5) ──────────────────────────────────────
    default_target_level: str = "AA"


settings = Settings()
