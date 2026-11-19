"""Local JSON trace of one analysis run (SERVICE_MVP.md 9.1, docs/decisions.md D4).

Written to data/traces/<trace_id>.json. Records node timings, LLM calls with
token usage and estimated cost, retrieval queries and documents, every
revalidation attempt, warnings, and errors.

Token usage comes from a LangChain callback, so the same tracer could later
feed another observability tool.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from a11y_investigator.config import settings


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """USD estimate from settings.model_prices (matched by 'sonnet' / 'haiku' in the model ID)."""
    for key, (price_in, price_out) in settings.model_prices.items():
        if key in model_id.lower():
            return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return 0.0


class TokenUsageCallback(BaseCallbackHandler):
    """Collects one record per chat-model call, tagged with the LangGraph node that made it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._pending: dict[UUID, dict[str, Any]] = {}

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, metadata=None, **kwargs) -> None:
        metadata = metadata or {}
        self._pending[run_id] = {
            "node": metadata.get("langgraph_node", ""),
            "model": (kwargs.get("invocation_params") or {}).get("model_id")
            or (kwargs.get("invocation_params") or {}).get("model", ""),
            "started": time.monotonic(),
        }

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs) -> None:
        pending = self._pending.pop(run_id, {"node": "", "model": "", "started": time.monotonic()})
        input_tokens = output_tokens = 0
        for generations in response.generations:
            for gen in generations:
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                input_tokens += usage.get("input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0)
        model = pending["model"] or (response.llm_output or {}).get("model_id", "") or settings.chat_model_id
        self.calls.append({
            "node": pending["node"],
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "seconds": round(time.monotonic() - pending["started"], 2),
            "estimated_cost_usd": round(estimate_cost(model, input_tokens, output_tokens), 6),
        })

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs) -> None:
        pending = self._pending.pop(run_id, {"node": "", "model": ""})
        self.calls.append({"node": pending["node"], "model": pending["model"], "error": f"{type(error).__name__}: {error}"[:300]})


class Tracer:
    """Pass to run_analysis(tracer=...). Collects node timings and LLM usage while the graph streams."""

    def __init__(self) -> None:
        self.callback = TokenUsageCallback()
        self.started_at = datetime.now(timezone.utc)
        self._t0 = time.monotonic()
        self._last = self._t0
        self.nodes: list[dict[str, Any]] = []
        self.revalidations: list[dict[str, Any]] = []

    def on_node_update(self, node: str, update: dict[str, Any]) -> None:
        now = time.monotonic()
        self.nodes.append({"node": node, "seconds": round(now - self._last, 2)})
        self._last = now
        if node == "revalidate" and update.get("revalidation_result"):
            self.revalidations.append(update["revalidation_result"])

    def build(self, state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
        calls = self.callback.calls
        input_tokens = sum(c.get("input_tokens", 0) for c in calls)
        output_tokens = sum(c.get("output_tokens", 0) for c in calls)
        return {
            "trace_id": state.get("trace_id"),
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "total_seconds": round(time.monotonic() - self._t0, 2),
            "outcome": report.get("outcome"),
            "input": {
                "project_id": state.get("project_id"),
                "code_type": state.get("code_type"),
                "target_level": state.get("target_level"),
                "component_hint": state.get("component_hint"),
                "user_request": state.get("user_request"),
                "code": state.get("input_code"),
            },
            "nodes": self.nodes,
            "llm": {
                "calls": calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": round(sum(c.get("estimated_cost_usd", 0.0) for c in calls), 6),
            },
            "retrieval": {
                "queries": state.get("retrieval_queries", []),
                "official": [d["document_id"] for d in state.get("official_documents", [])],
                "policies": [d["document_id"] for d in state.get("policy_documents", [])],
                "policies_reindexed": state.get("policies_reindexed", False),
            },
            "revalidations": self.revalidations,
            "warnings": state.get("warnings", []),
            "errors": state.get("errors", []),
            "versions": {
                "model": report.get("model"),
                "index_version": report.get("index_version"),
                "analyzer": report.get("analyzer_versions", {}),
            },
        }

    def save(self, trace: dict[str, Any], directory: Path | None = None) -> Path:
        directory = directory or settings.traces_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{trace['trace_id']}.json"
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
