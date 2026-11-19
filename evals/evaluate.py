"""Evaluation runner (SERVICE_MVP.md 9장).

    python -m evals.evaluate                       # all 19 cases + RAGAS
    python -m evals.evaluate --case button-01 --no-ragas
    python -m evals.evaluate --from-run evals/reports/<stamp>.json   # re-score / re-run RAGAS only

Runs every case through the real graph (Bedrock + Node), scores it against the
labels, runs RAGAS on the same saved state, and writes `evals/reports/<stamp>.json`
(full runs, re-scorable) and `<stamp>.md` (summary).
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from a11y_investigator.config import settings
from a11y_investigator.schemas.diagnosis import DiagnosisReport
from evals.dataset import EvalCase, load_cases
from evals.metrics import TARGETS, CaseResult, Usage, aggregate, score_case, usage_by_group

REPORTS_DIR = Path(__file__).parent / "reports"
STATE_KEYS = ("official_documents", "policy_documents", "static_result", "warnings")

app = typer.Typer(add_completion=False)


def run_case(case: EvalCase) -> dict[str, Any]:
    """Run one case through the graph; never raises."""
    from a11y_investigator.agent.graph import run_analysis
    from a11y_investigator.agent.trace import Tracer

    tracer = Tracer()
    t0 = time.monotonic()
    try:
        report, state = run_analysis(
            raw_input=case.request, file_code=case.code, project_id=case.project_id, tracer=tracer
        )
    except Exception as e:  # keep evaluating the other cases
        return {"case_id": case.id, "error": f"{type(e).__name__}: {e}"[:500],
                "usage": Usage(seconds=round(time.monotonic() - t0, 1)).model_dump()}
    trace = tracer.build(state, report.model_dump())
    tracer.save(trace)
    llm = trace["llm"]
    return {
        "case_id": case.id,
        "report": report.model_dump(),
        "state": {k: state.get(k) for k in STATE_KEYS},
        "documents": [
            {"document_id": d["document_id"], "text": d["text"]}
            for d in [*state.get("official_documents", []), *state.get("policy_documents", [])]
        ],
        "trace_id": trace["trace_id"],
        "usage": Usage(
            seconds=trace["total_seconds"], input_tokens=llm["input_tokens"], output_tokens=llm["output_tokens"],
            cost_usd=llm["estimated_cost_usd"], llm_calls=len(llm["calls"]),
        ).model_dump(),
    }


def score_run(case: EvalCase, run: dict[str, Any]) -> CaseResult:
    usage = Usage.model_validate(run.get("usage") or {})
    if run.get("error") or not run.get("report"):
        return CaseResult(
            id=case.id, component=case.component, category=case.category, code_type=case.code_type,
            outcome="error", expected_outcomes=list(case.expected.outcomes), outcome_ok=False,
            confirmed_expected=sum(f.status == "confirmed" for f in case.expected.findings),
            failures=[f"실행 오류: {run.get('error')}"], usage=usage,
        )
    return score_case(case, DiagnosisReport.model_validate(run["report"]), run["state"], usage)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.0%}" if value <= 1 else f"{value:.2f}"
    return str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    agg, ragas = summary["aggregate"], summary.get("ragas") or {}
    lines = [
        f"# 평가 결과 {summary['run_id']}",
        "",
        f"- 모델: `{summary['model']}` / RAGAS 평가 모델: `{ragas.get('judge_model') or '—'}`",
        f"- 인덱스: `{summary['index_version']}` / 케이스: {summary['cases']}개",
        "",
        "## 지표 (SERVICE_MVP.md 9.3)",
        "",
        "| 지표 | 결과 | 목표 | 통과 |",
        "|---|---|---|---|",
    ]
    names = {
        "confirmed_recall": "`confirmed` Finding 재현율",
        "clean_no_change_rate": "문제 없는 코드의 no-change 비율",
        "revalidation_pass_rate": "수정 시도 케이스의 재검증 통과율",
        "invalid_citations": "허위 인용 (존재하지 않는 문서·SC·규칙)",
        "wcag_mapping_accuracy": "WCAG 근거 연결 정확도",
    }
    for key, label in names.items():
        target, higher = TARGETS[key]
        goal = f"≥ {target:.0%}" if higher else f"{target}건"
        mark = {True: "✅", False: "❌", None: "—"}[agg["passed"][key]]
        lines.append(f"| {label} | {_fmt(agg['metrics'][key])} | {goal} | {mark} |")
    info = agg["info"]
    lines += [
        "",
        f"참고: outcome 정확도 {_fmt(info['outcome_accuracy'])}, suspected 탐지 {_fmt(info['suspected_detection'])}, "
        f"정책 판정 정확도 {_fmt(info['policy_accuracy'])}, 가드레일이 제거한 인용 {info['guardrail_removed']}건, "
        f"analysis_failed {info['analysis_failed']}건, 수정 시도 {info['fix_attempted']}건",
        "",
        "## RAGAS (진단 단계, 9.4)",
        "",
    ]
    if ragas.get("mean"):
        lines += [f"- {k}: {_fmt(v) if v is None else f'{v:.2f}'}" for k, v in ragas["mean"].items()]
        lines.append(f"- 대상: 문제 있음·정책 케이스 중 Finding이 나온 {ragas.get('samples', 0)}개")
    else:
        lines.append("- 실행하지 않음")
    lines += ["", "## 케이스별 결과", "", "| 케이스 | outcome | 기대 | 시도 | 실패 사유 |", "|---|---|---|---|---|"]
    for r in summary["results"]:
        mark = "✅" if not r["failures"] else "❌"
        lines.append(
            f"| {mark} {r['id']} | {r['outcome']} | {', '.join(r['expected_outcomes'])} | {r['attempts']} | "
            + ("<br>".join(f.replace("|", "\\|") for f in r["failures"]) or "—") + " |"
        )
    lines += ["", "## 케이스 유형별 평균 사용량", "", "| 유형 | 케이스 | 시간(초) | 입력 토큰 | 출력 토큰 | 예상 비용 | LLM 호출 |", "|---|---|---|---|---|---|---|"]
    for key, u in summary["usage"].items():
        lines.append(
            f"| {key} | {u['cases']} | {u['seconds']} | {u['input_tokens']:,} | {u['output_tokens']:,} | "
            f"${u['cost_usd']:.3f} | {u['llm_calls']} |"
        )
    total = summary["total_usage"]
    lines += ["", f"합계: {total['seconds']:.0f}초(케이스 합), 예상 비용 ${total['cost_usd']:.2f} (RAGAS 평가 호출 제외)", ""]
    return "\n".join(lines)


def summarize(cases: list[EvalCase], runs: dict[str, dict[str, Any]], ragas: dict[str, Any] | None, run_id: str) -> dict[str, Any]:
    by_id = {c.id: c for c in cases}
    results = [score_run(by_id[cid], runs[cid]) for cid in runs]
    return {
        "run_id": run_id,
        "model": settings.chat_model_id,
        "index_version": settings.index_version,
        "cases": len(results),
        "aggregate": aggregate(results),
        "ragas": ragas,
        "usage": usage_by_group(results),
        "total_usage": {
            "seconds": round(sum(r.usage.seconds for r in results), 1),
            "cost_usd": round(sum(r.usage.cost_usd for r in results), 4),
        },
        "results": [r.model_dump() for r in results],
    }


@app.command()
def main(
    case: list[str] = typer.Option(None, "--case", "-c", help="Case id prefix (repeatable). Default: all."),
    workers: int = typer.Option(2, help="Cases run in parallel (Bedrock throttling: keep small)."),
    no_ragas: bool = typer.Option(False, "--no-ragas", help="Skip RAGAS."),
    from_run: Path = typer.Option(None, "--from-run", help="Re-score a saved report JSON without re-running cases."),
    out_dir: Path = typer.Option(REPORTS_DIR, "--out-dir"),
) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    cases = load_cases()
    if case:
        cases = [c for c in cases if any(c.id.startswith(p) for p in case)]
    if not cases:
        raise typer.BadParameter("no matching cases")

    if from_run:
        saved = json.loads(from_run.read_text(encoding="utf-8"))
        runs = {cid: r for cid, r in saved["runs"].items() if any(c.id == cid for c in cases)}
    else:
        runs = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for run in pool.map(run_case, cases):
                runs[run["case_id"]] = run
                outcome = (run.get("report") or {}).get("outcome", "error")
                typer.echo(f"  {run['case_id']}: {outcome} ({run['usage']['seconds']}s)", err=True)

    ragas = None
    if not no_ragas:
        from evals.ragas_eval import build_sample, run_ragas

        by_id = {c.id: c for c in cases}
        samples = {cid: s for cid, r in runs.items() if (s := build_sample(by_id[cid], r))}
        typer.echo(f"RAGAS: {len(samples)} samples", err=True)
        ragas = run_ragas(samples)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    summary = summarize(cases, runs, ragas, run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{run_id}.json"
    json_path.write_text(json.dumps({**summary, "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = out_dir / f"{run_id}.md"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    typer.echo(render_markdown(summary))
    typer.echo(f"saved: {json_path} / {md_path}", err=True)


if __name__ == "__main__":
    app()
