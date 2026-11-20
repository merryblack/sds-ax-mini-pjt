"""Markdown rendering of DiagnosisReport for the CLI (SPEC_MVP.md 3.1).

Sections follow the nine report items:
1 요약 · 2 발견된 문제 · 3 근거 · 4 프로젝트 정책 · 5 개선 필요 여부 ·
6 개선 코드 · 7 변경 내용 · 8 재검증 · 9 수동 검증 항목
"""
from __future__ import annotations

from a11y_investigator.schemas.diagnosis import DiagnosisReport, DocumentEvidence, StaticEvidence

OUTCOME_LABEL = {
    "improved": "개선함 — 수정 코드가 재검증을 통과했습니다",
    "fix_failed": "개선 실패 — 수정 코드가 재검증을 통과하지 못했습니다",
    "no_change_needed": "수정하지 않음 — 자동 수정 대상이 없습니다",
    "no_issue_detected": "문제 없음 — 자동 검사에서 발견된 문제가 없습니다",
    "analysis_failed": "분석 실패",
}
STATUS_LABEL = {"confirmed": "확정", "suspected": "추정", "manual_review": "수동 확인"}
POLICY_LABEL = {
    "compliant": "준수",
    "violated": "위반",
    "conflict_with_wcag": "WCAG와 충돌 (WCAG 우선)",
    "not_applicable": "해당 없음",
}


def render_markdown(report: DiagnosisReport) -> str:
    lang = "tsx" if report.code_type == "tsx" else "jsx"
    out: list[str] = ["# 접근성 진단 보고서", ""]

    # 1. 요약
    out += ["## 1. 요약", "", report.overall_summary, ""]
    meta = f"목표 레벨: WCAG 2.2 {report.target_level}"
    if report.project_id:
        meta += f" · 프로젝트: `{report.project_id}`"
    out += [meta, ""]

    if report.outcome == "analysis_failed":
        out += ["## 5. 개선 필요 여부", "", f"**{OUTCOME_LABEL['analysis_failed']}**: {report.error}", ""]
        return _footer(out, report)

    # 2. 발견된 문제 / 3. 근거
    out += ["## 2. 발견된 문제", ""]
    if not report.findings:
        out += ["자동 검사에서 발견된 문제가 없습니다.", ""]
    for f in report.findings:
        fix = "수정 대상" if f.will_fix else "수정하지 않음"
        out += [
            f"### {f.id}. {f.title}",
            "",
            f"- 상태: **{STATUS_LABEL[f.status]}** · 심각도: {f.severity} · {fix}"
            + (f" · 위치: {f.location}" if f.location else ""),
            f"- WCAG: {', '.join(f.wcag_criteria) or '-'}",
            "",
            f.description,
            "",
            f"**권장사항:** {f.recommendation}",
            "",
        ]
    out += ["## 3. 근거", ""]
    rows = []
    for f in report.findings:
        for ev in f.evidence:
            if isinstance(ev, DocumentEvidence):
                url = report.sources.get(ev.document_id, "")
                rows.append(f"| {f.id} | 문서 | `{ev.document_id}` | {url} |")
            elif isinstance(ev, StaticEvidence):
                line = f"line {ev.line}" if ev.line else ""
                rows.append(f"| {f.id} | 정적 분석 | `{ev.rule_id}` | {line} |")
    out += (["| Finding | 종류 | 근거 | 출처 |", "|---|---|---|---|", *rows, ""] if rows else ["(근거 없음)", ""])

    # 4. 프로젝트 정책
    out += ["## 4. 프로젝트 정책 적합성", ""]
    if not report.project_id:
        out += ["프로젝트를 지정하지 않아 평가하지 않았습니다(`--project`).", ""]
    elif not report.policy_assessments:
        out += ["관련 정책이 없습니다.", ""]
    else:
        out += ["| 정책 | 결과 | 설명 |", "|---|---|---|"]
        out += [f"| `{p.policy_id}` | {POLICY_LABEL[p.status]} | {p.note} |" for p in report.policy_assessments]
        out += [""]

    # 5. 개선 필요 여부
    out += ["## 5. 개선 필요 여부", "", f"**{OUTCOME_LABEL[report.outcome]}**", ""]

    # 6. 개선 코드 / 7. 변경 내용
    if report.improved_code:
        out += ["## 6. 개선 코드", ""]
        if report.outcome == "fix_failed":
            out += ["> ⚠ 재검증을 통과하지 못한 **검증되지 않은 코드**입니다. 그대로 적용하지 마세요.", ""]
        out += [f"```{lang}", report.improved_code.rstrip("\n"), "```", ""]
        out += ["## 7. 변경 내용", ""]
        out += [f"- [{', '.join(c.finding_ids)}] {c.description}" for c in report.changes] or ["(기록 없음)"]
        out += [""]

    # 8. 재검증
    v = report.validation
    if v.status != "not_run":
        out += [
            "## 8. 재검증 결과",
            "",
            f"- 결과: **{'통과' if v.status == 'passed' else '실패'}** (시도 {v.attempts}회, 변경 {v.changed_lines}줄)",
            f"- 정적 분석 위반: {v.findings_before}건 → {v.findings_after}건",
        ]
        if v.new_findings:
            out += [f"- 새로 생긴 위반: {', '.join(f.rule_id for f in v.new_findings)}"]
        if v.remaining_rule_ids:
            out += [f"- 해소되지 않은 위반: {', '.join(v.remaining_rule_ids)}"]
        if v.blocked_patterns:
            out += [f"- 금지 패턴: {', '.join(v.blocked_patterns)}"]
        out += [""]

    # 9. 수동 검증
    out += ["## 9. 수동 검증 필요 항목", ""]
    out += [f"- {m}" for m in report.manual_checks] or ["(없음)"]
    out += [""]
    return _footer(out, report)


def _footer(out: list[str], report: DiagnosisReport) -> str:
    out += [
        "---",
        f"model `{report.model}` · index `{report.index_version}` · trace `{report.trace_id}`",
        "",
    ]
    return "\n".join(out)
