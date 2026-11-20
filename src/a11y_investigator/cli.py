"""CLI: `analyze`, `policies check`, `policies init` (SPEC_MVP.md 2.2, 6.2).

Exit codes for `analyze`: 0 = analysis completed (any outcome except analysis_failed),
1 = analysis_failed, 2 = bad command-line input.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from a11y_investigator.config import settings

app = typer.Typer(
    help="근거 기반 React 접근성 진단·개선 Agent (A11y Investigator).",
    no_args_is_help=True,
    add_completion=False,
)
policies_app = typer.Typer(help="프로젝트 정책(지침) 관리.", no_args_is_help=True)
app.add_typer(policies_app, name="policies")

LEVELS = ("A", "AA", "AAA")


def _utf8_stdout() -> None:
    """Korean text and ⚠ must print on Windows consoles that default to cp949."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


@app.command()
def analyze(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="분석할 React 파일 (.jsx / .tsx)."),
    request: str = typer.Option("", "--request", "-r", help="요청 문구 (예: 'AAA 기준으로 검토해 줘')."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="프로젝트 ID (정책 적용)."),
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="목표 레벨 A / AA / AAA. 생략하면 요청 문구 > 프로젝트 설정 > AA."
    ),
    json_output: bool = typer.Option(False, "--json", help="DiagnosisReport JSON으로 출력."),
    no_trace: bool = typer.Option(False, "--no-trace", help="Trace 파일을 남기지 않음."),
    trace_dir: Optional[Path] = typer.Option(None, "--trace-dir", help="Trace 저장 폴더 (기본 data/traces)."),
) -> None:
    """React 컴포넌트의 접근성을 진단하고, 필요하면 수정 코드를 생성·재검증한다.

    --file이 없으면 표준 입력에서 요청 문구와 코드(코드 블록)를 함께 읽는다.
    """
    _utf8_stdout()
    from a11y_investigator.agent.graph import run_analysis
    from a11y_investigator.agent.trace import Tracer
    from a11y_investigator.report_markdown import render_markdown

    if level is not None and level.upper() not in LEVELS:
        typer.echo(f"--level은 {', '.join(LEVELS)} 중 하나여야 합니다.", err=True)
        raise typer.Exit(code=2)

    if file is not None:
        if not file.is_file():
            typer.echo(f"파일을 찾을 수 없습니다: {file}", err=True)
            raise typer.Exit(code=2)
        file_code: str | None = file.read_text(encoding="utf-8")
        raw_input = request
    else:
        if sys.stdin.isatty():
            typer.echo("--file을 지정하거나 표준 입력으로 코드를 넘겨 주세요.", err=True)
            raise typer.Exit(code=2)
        file_code = None
        raw_input = (request + "\n" if request else "") + sys.stdin.read()

    tracer = None if no_trace else Tracer()
    report, state = run_analysis(
        raw_input=raw_input,
        file_code=file_code,
        project_id=project,
        level=level.upper() if level else None,  # type: ignore[arg-type]
        tracer=tracer,
    )

    if tracer is not None:
        trace = tracer.build(state, report.model_dump())
        path = tracer.save(trace, trace_dir)
        llm = trace["llm"]
        typer.echo(
            f"[trace] {path} · {trace['total_seconds']}s · tokens {llm['input_tokens']}+{llm['output_tokens']}"
            f" · ≈${llm['estimated_cost_usd']:.4f}",
            err=True,
        )

    typer.echo(report.model_dump_json(indent=2) if json_output else render_markdown(report))
    if report.outcome == "analysis_failed":
        raise typer.Exit(code=1)


@policies_app.command("init")
def policies_init(
    project_id: str = typer.Argument(..., help="새 프로젝트 ID (영문 소문자·숫자·하이픈)."),
    policies_dir: Optional[Path] = typer.Option(None, "--policies-dir", help="정책 루트 폴더 (기본 knowledge/project-policies)."),
) -> None:
    """템플릿으로 새 프로젝트 지침 폴더를 만들고 바로 검증한다. 이미 있는 폴더는 덮어쓰지 않는다."""
    _utf8_stdout()
    from a11y_investigator.tools.policy_lookup import PolicyError, init_project

    root = policies_dir or settings.policies_dir
    try:
        created = init_project(project_id, root)
    except PolicyError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"✓ 프로젝트 지침 폴더를 만들었습니다: {created[0].parent}")
    for path in created:
        typer.echo(f"  - {path.name}")
    typer.echo("")
    policies_check(project_id, policies_dir)
    typer.echo("")
    typer.echo("다음 단계")
    typer.echo("  1. project.yaml: 목표 레벨과 디자인 시스템 컴포넌트 매핑을 고친다.")
    typer.echo("  2. btn-001.md: 예시 정책을 실제 규칙으로 고치거나, 규칙마다 .md 파일을 추가한다.")
    typer.echo(f"  3. 검증: python a11y.py policies check {project_id}")
    typer.echo(f"  4. 분석: python a11y.py analyze --file <컴포넌트 파일> --project {project_id}")


@policies_app.command("check")
def policies_check(
    project_id: str = typer.Argument(..., help="검증할 프로젝트 ID (knowledge/project-policies/<project_id>)."),
    policies_dir: Optional[Path] = typer.Option(None, "--policies-dir", help="정책 루트 폴더 (기본 knowledge/project-policies)."),
) -> None:
    """프로젝트 정책 폴더의 형식·ID·컴포넌트·WCAG 번호를 검증한다. 문제가 있으면 종료 코드 1."""
    _utf8_stdout()
    from a11y_investigator.middleware.safety import indexed_sc
    from a11y_investigator.tools.policy_lookup import check_project

    root = policies_dir or settings.policies_dir
    policies, problems = check_project(project_id, root, known_sc=indexed_sc())
    if problems:
        typer.echo(f"✗ {project_id}: 문제 {len(problems)}건")
        for p in problems:
            typer.echo(f"  - {p}")
        raise typer.Exit(code=1)
    typer.echo(f"✓ {project_id}: 정책 {len(policies)}개, 문제 없음")
    for p in policies:
        typer.echo(f"  - {p.policy_id} ({', '.join(p.applies_to) or '-'}) {p.title}")


if __name__ == "__main__":
    app()
