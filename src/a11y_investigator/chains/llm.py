"""Bedrock chat model factory (docs/decisions.md D1)."""
from __future__ import annotations

from functools import lru_cache

from botocore.config import Config
from langchain_aws import ChatBedrockConverse

from a11y_investigator.config import settings

# Retry throttling / transient errors at the client level (adaptive backoff).
_BOTO_CONFIG = Config(retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=120)


@lru_cache(maxsize=4)
def get_chat_model(light: bool = False, max_tokens: int = 4096) -> ChatBedrockConverse:
    """Claude Sonnet 4.6 by default; `light=True` uses Haiku 4.5 (cheaper, for repeated evals)."""
    return ChatBedrockConverse(
        model=settings.chat_model_id_light if light else settings.chat_model_id,
        region_name=settings.aws_region,
        temperature=settings.temperature,
        max_tokens=max_tokens,
        config=_BOTO_CONFIG,
    )
