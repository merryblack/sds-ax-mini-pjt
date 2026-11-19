"""Embeddings and Chroma collections (SERVICE_MVP.md 6.4, docs/decisions.md D2)."""
from __future__ import annotations

import threading
from functools import lru_cache

from chromadb.config import Settings as ChromaSettings
from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma

from a11y_investigator.config import settings

EMBEDDING_DIMENSIONS = 1024

# Chroma's shared client registry is not safe to initialize from several threads at once
# (seen in parallel evaluation runs: KeyError / missing Rust bindings on first open).
_CHROMA_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def get_embeddings() -> BedrockEmbeddings:
    """Amazon Titan Text Embeddings V2 on Bedrock (normalized, 1024 dims)."""
    return BedrockEmbeddings(
        model_id=settings.embedding_model_id,
        region_name=settings.embedding_region,
        model_kwargs={"dimensions": EMBEDDING_DIMENSIONS, "normalize": True},
    )


def get_collection(name: str) -> Chroma:
    """Open (or create) a persistent Chroma collection using cosine distance."""
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    with _CHROMA_LOCK:
        return _open_collection(name)


def _open_collection(name: str) -> Chroma:
    return Chroma(
        collection_name=name,
        embedding_function=get_embeddings(),
        persist_directory=str(settings.chroma_dir),
        collection_metadata={
            "hnsw:space": "cosine",
            "embedding_model": settings.embedding_model_id,
            "index_version": settings.index_version,
        },
        client_settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
    )
