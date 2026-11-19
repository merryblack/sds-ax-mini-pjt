"""RAGAS on the diagnosis step (SERVICE_MVP.md 9.4).

Inputs come from the saved graph state, so no extra diagnosis calls are made.
Uses the ragas 0.4 `evaluate()` API with LangChain wrappers around Bedrock
(Haiku 4.5 as judge, Titan V2 embeddings). These metric classes are marked
deprecated in ragas 0.4 (to be replaced by `ragas.metrics.collections` in 1.0);
the version is pinned in requirements.txt.
"""
from __future__ import annotations

import math
import warnings
from typing import Any

from evals.dataset import EvalCase

METRICS = ("context_recall", "llm_context_precision_with_reference", "faithfulness", "answer_relevancy")
SHORT = {
    "context_recall": "context_recall",
    "llm_context_precision_with_reference": "context_precision",
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
}


def build_sample(case: EvalCase, run: dict[str, Any]) -> dict[str, Any] | None:
    """RAGAS row for one case, or None when there is nothing to judge (clean case or no findings).

    `retrieved_contexts` holds only the retrieved documents (for the retrieval metrics).
    `grounding_contexts` adds the code and static analysis result the diagnosis LLM also
    received, so faithfulness can verify claims about the code itself.
    """
    if case.category == "clean" or not case.expected.findings:
        return None
    findings = (run.get("report") or {}).get("findings") or []
    contexts = [d["text"] for d in run.get("documents", []) if d.get("text")]
    if not findings or not contexts:
        return None
    response = "\n".join(
        f"- {f['title']}: {f['description']} 권장: {f['recommendation']}" for f in findings
    )
    reference = "\n".join(f"- {f.description}" for f in case.expected.findings)
    static = ((run.get("state") or {}).get("static_result") or {}).get("findings") or []
    static_text = "[정적 분석 결과]\n" + (
        "\n".join(f"- {f['rule_id']} (line {f.get('line')}): {f.get('message', '')}" for f in static) or "- 없음"
    )
    code_text = f"[분석 대상 코드]\n```{case.code_type}\n{case.code}\n```"
    return {
        "user_input": f"{case.request}\n\n```{case.code_type}\n{case.code}\n```",
        "retrieved_contexts": contexts,
        "grounding_contexts": [code_text, static_text, *contexts],
        "response": response,
        "reference": reference,
    }


def _clean(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 3)


def run_ragas(samples: dict[str, dict[str, Any]], max_workers: int = 4) -> dict[str, Any]:
    """Score samples (case_id -> row). Returns per-case scores and the mean of each metric."""
    if not samples:
        return {"per_case": {}, "mean": {}, "judge_model": None}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from ragas import EvaluationDataset, RunConfig, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )

    from a11y_investigator.chains.llm import get_chat_model
    from a11y_investigator.config import settings
    from a11y_investigator.rag.store import get_embeddings

    ids = list(samples)
    llm = LangchainLLMWrapper(get_chat_model(light=True))
    embeddings = LangchainEmbeddingsWrapper(get_embeddings())
    run_config = RunConfig(max_workers=max_workers, timeout=300, max_retries=5)

    def rows_of(context_key: str, metrics: list) -> list[dict[str, Any]]:
        dataset = EvaluationDataset.from_list([
            {k: samples[i][k] for k in ("user_input", "response", "reference")}
            | {"retrieved_contexts": samples[i][context_key]}
            for i in ids
        ])
        result = evaluate(dataset, metrics=metrics, llm=llm, embeddings=embeddings,
                          run_config=run_config, show_progress=False)
        return result.to_pandas().to_dict(orient="records")

    retrieval = rows_of("retrieved_contexts", [LLMContextRecall(), LLMContextPrecisionWithReference()])
    grounding = rows_of("grounding_contexts", [Faithfulness(), ResponseRelevancy()])
    per_case = {
        case_id: {SHORT[m]: _clean({**r1, **r2}.get(m)) for m in METRICS}
        for case_id, r1, r2 in zip(ids, retrieval, grounding)
    }
    mean = {}
    for m in METRICS:
        values = [v[SHORT[m]] for v in per_case.values() if v[SHORT[m]] is not None]
        mean[SHORT[m]] = round(sum(values) / len(values), 3) if values else None
    return {"per_case": per_case, "mean": mean, "judge_model": settings.chat_model_id_light, "samples": len(ids)}
