# A11y Investigator — Service MVP

**2~3일 MVP 구현 명세**

| 항목 | 내용 |
|---|---|
| 대상 | 제품 V0.2 (MVP), P0 범위만 |
| 개발 기간 | 2~3일 |
| 상위 문서 | [ROADMAP.md](ROADMAP.md) — 배경, 설계 원칙, 제품 범위, 우선순위, P1 상세, V0.3 이후 계획 |

이 문서만 보고 MVP를 구현할 수 있도록 P0에 필요한 내용만 모았다. P1 항목은 이름만 표시하고 상세는 다루지 않는다.

---

# 1. 목표와 범위

## 1.1. 핵심 기능

**사용자가 CLI로 React(JSX/TSX) 컴포넌트 코드를 입력하면, Agent가 접근성 문제를 검증하고 개선 필요 여부를 판단한 후 필요한 경우 개선된 전체 코드를 출력한다.**

- 로컬 프로젝트 파일은 읽거나 수정하지 않는다. 사용자가 입력한 코드만 분석한다.
- 입력 규모는 단일 React 컴포넌트이다.
- HTML 및 HTML + JavaScript 입력은 일정상 MVP에서 제외하고 V0.3에서 지원한다([ROADMAP.md](ROADMAP.md)).
- 지원 컴포넌트: Button, Dialog, Tabs, Combobox

## 1.2. 지켜야 할 원칙

설계 원칙의 상세는 [ROADMAP.md 2장](ROADMAP.md)을 따른다. 구현 시 특히 지킬 것:

- **필수 단계는 LLM이 아니라 고정된 그래프 노드로 실행한다.** 정적 분석, 매핑, 검색, 판단, 재검증은 항상 실행된다.
- **근거 없는 판정은 하지 않는다.** 근거가 없으면 `manual_review`로 분류한다.
- **검증 결과와 출처 URL은 일반 코드가 채운다.** LLM이 지어내지 못하게 한다.
- **최소 수정.** 접근성 개선에 필요한 부분만 바꾸고 기능·구조·스타일은 유지한다.
- **"접근성 완전 준수" 같은 표현은 쓰지 않는다.** 정적 분석 통과는 수행한 검사 범위 안의 통과일 뿐이다.

## 1.3. 범위 밖

| 구분 | 항목 |
|---|---|
| P1 stretch (시간이 남으면) | ReAct 추가 조사, MCP 서버, RAGAS, LLM-as-Judge, FastAPI, 민감정보 마스킹, Hybrid Retrieval / Reranking |
| MVP 제외 | HTML / HTML + JS 입력, 로컬 파일 수정, 브라우저·동적 분석, 스크린리더 테스트, Multi-Agent, 장기 메모리, 문서 동기화 자동화 |

---

# 2. 입력

## 2.1. 지원 입력

| `code_type` | 입력 |
|---|---|
| `jsx` | React JSX |
| `tsx` | React TSX |

TypeScript 문법(타입 표기, `interface`, 제네릭 등)이 있으면 `tsx`, 없으면 `jsx`로 판별한다. JSX가 아닌 코드(순수 HTML 등)는 `analysis_failed`와 "MVP는 React 코드만 지원" 사유를 반환한다.

## 2.2. CLI

```text
a11y-investigator analyze [--file Component.tsx] [--project demo-ds] [--level AA] [--json]
```

- `--file`이 없으면 표준 입력에서 자연어 요청과 코드를 함께 받는다.
- `--project`를 지정하지 않으면 정책 검색과 정책 적합성 평가를 건너뛴다.

## 2.3. 입력 제한

| 항목 | 값 |
|---|---|
| 코드 최대 길이 | 300줄 또는 약 8,000 토큰 중 작은 값 |
| 코드 블록 수 | 1개 |
| 초과 시 동작 | 분석하지 않고 `analysis_failed`와 사유를 반환 |

## 2.4. 코드 추출 규칙

1. `--file`로 코드를 전달했으면 그 내용을 코드로 사용한다.
2. Markdown 코드 펜스가 있으면 그 내용을 코드로, 나머지를 `user_request`로 사용한다.
3. 코드 펜스가 2개 이상이면 분석하지 않고 하나만 입력하도록 안내한다.
4. 코드 펜스가 없으면 첫 번째 `import`, `export`, `function`, `const` 등으로 시작하는 줄부터 끝까지를 코드로 간주한다.

## 2.5. 분석 기준

| 항목 | 기본값 | 변경 방법 |
|---|---|---|
| 목표 적합성 레벨 | WCAG 2.2 **AA** | `--level`, 요청 문구, 프로젝트 `target_level` |
| 출력 언어 | 한국어 (코드·규칙 ID·WCAG 명칭은 원문 유지) | — |

목표 레벨보다 높은 레벨의 기준은 위반으로 판정하지 않고 참고 사항으로만 표시한다.

## 2.6. 컴포넌트 힌트

검색 범위를 좁히기 위해 `parse_input`에서 LLM 없이 컴포넌트 유형을 추정한다(`component_hint`).

| 단서 | 예 | 힌트 |
|---|---|---|
| `role` 속성 | `role="dialog"`, `role="tablist"`, `role="combobox"` | dialog / tabs / combobox |
| 컴포넌트·함수 이름 | `Dialog`, `Modal`, `Tabs`, `Combobox`, `Select`, `*Button` | dialog / tabs / combobox / button |
| 요소 | `<dialog>`, `<button>`, `onClick`이 붙은 `div` | dialog / button |

여러 개가 걸리면 모두 기록하고, 아무것도 없으면 `null`로 둔다.

---

# 3. 출력

## 3.1. 보고서 항목

1. 진단 요약
2. 발견된 문제와 상태 (confirmed / suspected / manual_review)
3. 각 문제의 근거 (공식 문서, 정적 분석 결과)
4. 프로젝트 정책 적합성 (`--project` 지정 시)
5. 개선 필요 여부
6. 개선된 전체 코드 (필요한 경우)
7. 변경 내용과 이유
8. 재검증 결과
9. 수동 검증 필요 항목

CLI는 기본으로 Markdown 보고서를, `--json`이면 `DiagnosisReport`(7.2) JSON을 출력한다.

## 3.2. 결과 유형 (`outcome`)

| 값 | 의미 |
|---|---|
| `improved` | 수정 코드를 생성했고 재검증을 통과함 |
| `fix_failed` | 재시도 한도 내에 재검증을 통과하지 못함 |
| `no_change_needed` | 문제 후보는 있으나 모두 수동 검증 대상이라 코드를 변경하지 않음 |
| `no_issue_detected` | 문제를 발견하지 못함 |
| `analysis_failed` | 입력 제한 초과, 코드 추출 실패, 분석기 오류 등으로 진단 불가 |

## 3.3. 시나리오

### A — 개선이 필요한 코드

```jsx
export default function SaveButton() {
  return <div onClick={() => alert("saved")}>저장</div>;
}
```

`jsx-a11y/click-events-have-key-events`, `jsx-a11y/no-static-element-interactions` 검출 → WCAG 2.1.1, 4.1.2 근거 조회 → `confirmed` → 수정 → 재검증 통과 → `improved`.

```jsx
export default function SaveButton() {
  return (
    <button type="button" onClick={() => alert("saved")}>
      저장
    </button>
  );
}
```

### B — 개선이 불필요한 코드

원본을 유지하고 `no_issue_detected`(또는 `no_change_needed`)와 함께 정적 분석으로 확인할 수 없는 수동 검증 항목을 출력한다.

### C — 프로젝트 정책 적용

`--project demo-ds`이고 정책이 `<Button>` 사용을 요구하면, WCAG 적합성과 정책 적합성을 따로 평가한다. 출력 코드는 다음 순서로 결정한다.

1. 정책과 WCAG를 모두 만족하는 방법이 있으면 그 방법으로 수정한다. 예: `<div>` → `<Button>`
2. 둘 다 만족할 수 없으면 **WCAG를 우선**해 수정하고, 정책을 `conflict_with_wcag`로 보고하며 정책 변경이나 예외 승인을 대안으로 제시한다.

---

# 4. 아키텍처

## 4.1. 그래프 흐름

```text
parse_input ─(실패)─────────────────────────────┐
     │                                          │
  analyze ───(분석기 오류)──────────────────────┤
     │                                          │
  map_rules → retrieve → diagnose → decide      │
                                      │         │
                    needs_improvement=false ────┤
                                      │         │
                                generate_fix ◄──┼──┐
                                      │         │  │ 실패 & retry < 2
                                 revalidate ────┼──┘
                                      │         │
                       통과 또는 (실패 & retry ≥ 2)
                                      v         v
                                    report ◄────┘
```

- 그래프 전체에 `recursion_limit=25`를 설정한다.
- 관측(Trace)과 Guardrails는 모든 노드에 걸쳐 적용한다.

## 4.2. 노드

| 노드 | 구현 | 역할 |
|---|---|---|
| `parse_input` | `detect_code_type` | 코드 추출, 유형 식별, 컴포넌트 힌트, 입력 제한 검사 (2장) |
| `analyze` | `analyze_code` | Node 정적 분석기 실행 (5.1) |
| `map_rules` | `map_rules_to_wcag` | 규칙 ID → WCAG SC / APG 패턴 (6.3) |
| `retrieve` | `search_guidelines`, `get_wcag_criterion`, `get_project_policy` | 공식 문서·정책 검색 (6.5) |
| `diagnose` | LCEL 체인 → `DiagnosisOutput` | 문제 진단, 정책 적합성 평가 |
| `decide` | 일반 코드 | 상태 보정과 수정 여부 결정 (5.2) |
| `generate_fix` | LCEL 체인 → `FixOutput` | 수정된 전체 코드 생성 |
| `revalidate` | `validate_generated_code` | 재검증과 재시도 판단 (5.3) |
| `report` | 일반 코드 | `DiagnosisReport` 조립, 근거 URL·검증 결과 채움 |

---

# 5. 핵심 로직

## 5.1. 정적 분석기

| 입력 | 도구 |
|---|---|
| JSX | ESLint 9 (flat config) + `eslint-plugin-jsx-a11y` (`recommended`) |
| TSX | 위와 동일 + `@typescript-eslint/parser` (타입 정보 없이 구문 파싱만) |

### Python ↔ Node 인터페이스

- `node analyzer-js/analyze.mjs --type <code_type>`를 subprocess로 실행한다.
- 코드는 stdin으로 넘기고, 결과는 stdout의 JSON 한 개(`AnalyzerResult`)로 받는다.
- 타임아웃 20초. 초과하거나 종료 코드가 0이 아니면 `analysis_failed`.
- 임시 파일은 OS 임시 디렉터리를 쓰고 경로는 `pathlib`으로 처리한다(Windows 호환).
- 결과에 분석기 버전을 포함한다.

### 파싱 실패

`parse_ok=false`로 진행한다. LLM 진단은 하되 `confirmed`는 나올 수 없고 코드 수정도 하지 않는다. `outcome`은 Finding이 있으면 `no_change_needed`, 없으면 `no_issue_detected`이며, 보고서에 파싱 실패 사유를 표시한다.

### 커스텀 컴포넌트 매핑

프로젝트의 `component_mapping`(6.2)을 ESLint `settings['jsx-a11y'].components`로 주입해, `<Button>` 같은 디자인 시스템 컴포넌트를 네이티브 요소로 인식시킨다.

## 5.2. 판단 규칙 (`decide`)

### Finding 상태

| 상태 | 조건 |
|---|---|
| `confirmed` | 정적 분석이 직접 뒷받침하거나 코드에서 결정적으로 확인 가능. 공식 문서 근거 1개 이상 |
| `suspected` | 정적 분석 결과는 없지만 코드 맥락으로 추론. 공식 문서 근거 1개 이상 |
| `manual_review` | 근거가 없거나 렌더링·실행·보조기기 확인이 필요 (예: 색 대비) |

근거 문서가 없는 `confirmed` / `suspected`는 `manual_review`로 강등한다.

### 수정 여부

| 상태 | 수정 |
|---|---|
| `confirmed` | 수정한다 |
| `suspected` | `fix_scope="local"`일 때만 수정한다. `structural`(상태 관리나 구조 변경 필요)이면 권장사항으로만 제시한다 |

`decide`는 수정 전에 실행되므로 변경 범위를 직접 알 수 없다. 그래서 진단 체인이 `suspected` Finding마다 `fix_scope`를 함께 출력하고, `decide`는 이 값으로 판단한다. 값이 없으면 `structural`로 간주한다.
| `manual_review` | 수정하지 않는다 |

수정 대상(`will_fix=true`)이 1개 이상이면 `needs_improvement=true`이다.

## 5.3. 재검증 (`revalidate`)

### 통과 기준 (모두 만족)

1. 수정 코드의 파싱이 성공한다.
2. 원본에 없던 규칙 위반이 새로 생기지 않는다. 수정 후에는 줄 번호가 바뀌므로 `rule_id`별 위반 개수로 비교한다(어떤 규칙이든 원본보다 개수가 늘면 실패).
3. `will_fix=true`인 Finding과 연결된 규칙 위반이 모두 해소된다.
4. 원본에 없던 린트 우회 주석이 없다(8장).

### 재시도

- 재수정은 **최대 2회**이다(총 3회 시도).
- 재수정 시 이전 실패 사유(새 위반, 미해소 규칙, 금지 패턴)를 `generate_fix`에 전달한다.
- 한도를 넘으면 `fix_failed`로 종료한다. `improved_code`에 마지막 시도 코드를 넣고 "검증되지 않은 코드" 경고와 미해결 항목을 표시한다.

---

# 6. 지식베이스

## 6.1. 수집 범위

| 문서 | 범위 | 출처 |
|---|---|---|
| WCAG 2.2 | 매핑 테이블의 SC 13개 + 컴포넌트 관련 SC 7개(1.4.3, 1.4.11, 2.1.2, 2.4.7, 2.4.11, 2.5.3, 4.1.3) = 20개 | W3C 공식 JSON (`https://www.w3.org/WAI/WCAG22/wcag.json`) |
| Understanding | 위 SC 20개의 문서 | GitHub `w3c/wcag` |
| Techniques | 위 SC의 Sufficient Techniques 중 ARIA / Script / HTML (57개) | GitHub `w3c/wcag` |
| APG | Button, Dialog (Modal), Tabs, Combobox | GitHub `w3c/aria-practices` |

모든 근거에 출처 URL을 표기한다(W3C Document License). 수집은 `python -m a11y_investigator.rag.fetch`로 하고, 수집 출처와 커밋 해시는 `knowledge/manifests/sources.yaml`에 자동 기록한다. 결과는 청크 340개다(WCAG 20, Understanding 150, Techniques 145, APG 25).

## 6.2. 프로젝트 정책

`knowledge/project-policies/<project_id>/`에 둔다. 시연용 프로젝트는 가상 디자인 시스템 `demo-ds`이며 정책 5개를 둔다.

| policy_id | 내용 | 용도 |
|---|---|---|
| `demo-ds-btn-001` | 클릭 요소는 `<Button>` 사용, 네이티브 `<button>` 직접 사용 금지 | Scenario C 기본 케이스 |
| `demo-ds-icon-001` | 아이콘 버튼은 `<IconButton>` + `aria-label` | 정책 준수 확인 |
| `demo-ds-dialog-001` | 모달은 `<Dialog>`, 포커스 이동·복귀, Escape로 닫기 | Dialog 정책 |
| `demo-ds-tabs-001` | `<Tabs>` 묶음 사용, 화살표 키 이동 | Tabs 정책 |
| `demo-ds-focus-001` | 포커스 아웃라인 제거(`outline: none`) | **의도적으로 WCAG 2.4.7과 충돌** → `conflict_with_wcag` 확인 |

`project.yaml`:

```yaml
project_id: demo-ds
target_level: AA
component_mapping:
  Button: button
  Link: a
  TextField: input
```

정책 규칙 (규칙 하나당 Markdown 파일 하나):

```markdown
---
policy_id: demo-ds-btn-001
project_id: demo-ds
title: 버튼은 디자인 시스템 Button 컴포넌트를 사용한다
applies_to: [button]
related_wcag: ["4.1.2", "2.1.1"]
---
클릭 가능한 요소는 `@demo-ds/ui`의 `<Button>`을 사용한다. 네이티브 `<button>` 직접 사용은 금지한다.
```

## 6.3. 규칙–WCAG 매핑

정적 분석 규칙에는 WCAG 정보가 없으므로 `knowledge/manifests/rule-wcag-map.yaml`을 수작업으로 작성한다. jsx-a11y `recommended`에서 켜진 규칙 31개 전체를 `rules:` 목록으로 매핑한다(아래는 일부).

```yaml
- rule_id: jsx-a11y/click-events-have-key-events
  tool: eslint-jsx-a11y
  wcag: ["2.1.1"]
  apg_pattern: button
  default_severity: serious
- rule_id: jsx-a11y/no-static-element-interactions
  tool: eslint-jsx-a11y
  wcag: ["2.1.1", "4.1.2"]
  apg_pattern: button
  default_severity: serious
- rule_id: jsx-a11y/role-has-required-aria-props
  tool: eslint-jsx-a11y
  wcag: ["4.1.2"]
  apg_pattern: null
  default_severity: serious
```

- `StaticFinding.wcag_refs`를 채우고, 정확 조회의 키와 평가 정답으로 쓴다.
- 매핑에 없는 규칙은 경고 로그를 남기고 벡터 검색만 사용한다.
- 매핑의 모든 SC ID가 인덱싱된 SC 목록에 있는지 테스트로 검증한다.

## 6.4. 청킹과 메타데이터

| 문서 | 청크 단위 |
|---|---|
| WCAG | 성공 기준별 |
| Understanding | 기준 및 하위 섹션별 |
| Techniques | 기법 ID별 |
| APG | 패턴 및 하위 섹션별 |
| Project Policy | 정책 규칙별 |

```json
{
  "document_id": "apg-dialog-keyboard",
  "source_type": "official_guide",
  "source_name": "WAI-ARIA APG",
  "component": "dialog",
  "section": "Keyboard Interaction",
  "wcag_sc": "2.1.1,2.4.3",
  "wcag_level": "A",
  "project_id": null,
  "index_version": "index-v1",
  "source_url": "https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/"
}
```

- Chroma 메타데이터는 스칼라만 허용하므로 리스트는 쉼표 문자열로 저장한다.
- WCAG SC 문서의 `document_id`는 `wcag-<SC>` 형식으로 정확 조회한다(예: `wcag-2.1.1`).
- 컬렉션은 `official`, `project_policies` 두 개이며, 정책 검색에는 항상 `project_id` 필터를 건다.

## 6.5. 검색 (`retrieve`)

1. `wcag_refs`와 APG 패턴으로 **정확 조회**한다.
2. `component_hint`, 규칙 ID, 정적 분석 메시지로 **영어 쿼리**를 만들어 벡터 검색한다(공식 문서가 영어이므로). 쿼리는 LLM 없이 템플릿으로 만든다. 예: `"{component} accessibility {rule_id} {message}"`. 정적 분석 결과가 없으면 `"{component} keyboard interaction ARIA"`로 검색한다.
3. `project_id`가 있으면 정책 컬렉션을 검색한다(한국어 원문 그대로).

LLM에는 공식 문서 최대 6개, 정책 최대 4개 청크를 전달한다.

## 6.6. 인덱싱

`rag/ingest.py`를 수동 실행해 전체를 다시 인덱싱한다.

```text
GitHub 원본 → Parser / Normalizer → Semantic Chunker → Embedding → Chroma
```

---

# 7. 상태와 스키마

## 7.1. 그래프 상태

```python
import operator
from typing import Annotated, Any, Literal, TypedDict

CodeType = Literal["jsx", "tsx"]

class AnalysisState(TypedDict, total=False):
    # 입력
    raw_input: str
    user_request: str
    input_code: str
    code_type: CodeType
    project_id: str | None
    target_level: Literal["A", "AA", "AAA"]
    component_hint: list[str] | None              # 2.6

    # 분석
    static_result: dict[str, Any]                 # AnalyzerResult
    official_documents: list[dict[str, Any]]
    policy_documents: list[dict[str, Any]]

    # 판단
    diagnosis: dict[str, Any]                     # DiagnosisOutput
    needs_improvement: bool

    # 수정 루프
    improved_code: str | None
    revalidation_result: dict[str, Any] | None    # ValidationResult
    retry_count: int

    # 공통
    report: dict[str, Any] | None                 # DiagnosisReport
    errors: Annotated[list[str], operator.add]    # reducer 필수: 없으면 덮어써짐
    trace_id: str
```

## 7.2. 스키마

세 그룹으로 나눈다. **정적 분석 결과**는 Node 분석기가, **LLM 출력**은 체인의 구조화 출력이 만든다. **최종 보고서**는 일반 코드가 조립한다.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field

CodeType = Literal["jsx", "tsx"]
Severity = Literal["critical", "serious", "moderate", "minor"]

# ── 정적 분석 결과 ──────────────────────────────
class StaticFinding(BaseModel):
    tool: Literal["eslint-jsx-a11y"]
    rule_id: str
    message: str
    line: int | None = None
    column: int | None = None
    element: str | None = None
    wcag_refs: list[str] = []           # 매핑 테이블로 채움

class AnalyzerResult(BaseModel):
    parse_ok: bool
    parse_error: str | None = None
    findings: list[StaticFinding]
    analyzer_versions: dict[str, str]

# ── 근거 ────────────────────────────────────────
class DocumentEvidence(BaseModel):
    kind: Literal["document"] = "document"
    document_id: str                    # URL은 코드가 메타데이터에서 채움
    source_type: Literal["official", "project_policy"]
    section: str | None = None

class StaticEvidence(BaseModel):
    kind: Literal["static_analysis"] = "static_analysis"
    tool: str
    rule_id: str
    line: int | None = None

Evidence = Annotated[DocumentEvidence | StaticEvidence, Field(discriminator="kind")]

# ── LLM 출력 ────────────────────────────────────
class Finding(BaseModel):
    id: str                             # "F1", "F2", ...
    title: str
    description: str
    status: Literal["confirmed", "suspected", "manual_review"]
    severity: Severity
    wcag_criteria: list[str]
    location: str | None = None         # 예: "L3-L5"
    fix_scope: Literal["local", "structural"] | None = None   # suspected일 때 필수 (5.2)
    evidence: list[Evidence]
    recommendation: str

class PolicyAssessment(BaseModel):
    policy_id: str
    status: Literal["compliant", "violated", "conflict_with_wcag", "not_applicable"]
    note: str

class DiagnosisOutput(BaseModel):
    findings: list[Finding]
    policy_assessments: list[PolicyAssessment]
    manual_checks: list[str]

class CodeChange(BaseModel):
    finding_ids: list[str]
    description: str

class FixOutput(BaseModel):
    improved_code: str
    changes: list[CodeChange]

# ── 최종 보고서 (일반 코드가 조립) ────────────────
class ValidationResult(BaseModel):
    status: Literal["passed", "failed", "not_run"]
    attempts: int                       # not_run이면 0, 그 외 1~3
    findings_before: int
    findings_after: int
    new_findings: list[StaticFinding]
    remaining_rule_ids: list[str]
    blocked_patterns: list[str]
    changed_lines: int                  # 불필요한 변경 추적 (8장)

class FindingResult(Finding):
    will_fix: bool                      # decide 노드가 설정

class DiagnosisReport(BaseModel):
    outcome: Literal["improved", "fix_failed", "no_change_needed",
                     "no_issue_detected", "analysis_failed"]
    code_type: CodeType | None
    target_level: Literal["A", "AA", "AAA"]
    project_id: str | None
    findings: list[FindingResult]
    policy_assessments: list[PolicyAssessment]
    improved_code: str | None           # improved / fix_failed일 때만
    changes: list[CodeChange]
    validation: ValidationResult
    manual_checks: list[str]
    sources: dict[str, str]             # document_id → source_url (report가 메타데이터에서 채움)
    overall_summary: str
    error: str | None = None
    # 재현성
    model: str
    index_version: str
    analyzer_versions: dict[str, str]
    trace_id: str
```

LLM은 전달받은 `document_id`만 인용할 수 있다. 그 외 ID는 `report`에서 제거하고, 근거가 남지 않은 Finding은 `manual_review`로 강등한다.

---

# 8. Guardrails

| 항목 | 구현 |
|---|---|
| 코드·문서 내 프롬프트 인젝션 | 입력 코드와 검색 문서를 구분 태그로 감싸고, 그 안의 지시문은 데이터로만 취급하도록 시스템 프롬프트에 명시 |
| 허위 출처·존재하지 않는 WCAG ID | `wcag_criteria`를 인덱싱된 SC 목록과 대조, 전달되지 않은 `document_id` 제거 |
| 근거 없는 위반 판정 | 근거 없는 Finding을 `manual_review`로 강등 |
| 린트 우회 | 원본에 없던 `eslint-disable`(`-next-line`, `-line` 포함) 주석이 있으면 재검증 실패 |
| 불필요한 변경 | 변경 줄 수를 기록해 보고서와 평가에 사용 |
| 프로젝트 간 지식 혼입 | 정책 검색에 `project_id` 필터 강제 |

---

# 9. 관측과 평가

## 9.1. Trace 기록 항목

노드별 실행 시간, Tool 호출, 검색된 문서, LLM 입출력 토큰, 예상 비용, 개선 여부, 재검증 결과, 인덱스·분석기 버전.

## 9.2. 평가 데이터셋

`evals/datasets/`에 19개를 작성한다. JSX와 TSX를 섞어 구성한다(최소 4개는 TSX).

| 컴포넌트 | 문제 있음 | 문제 없음 | 정책 적용 |
|---|---|---|---|
| Button | 4 | 2 | 2 |
| Dialog | 3 | 1 | — |
| Tabs | 3 | 1 | — |
| Combobox | 2 | 1 | — |
| **합계** | **12** | **5** | **2** |

케이스마다 기대 Finding(`rule_id` 또는 설명, `status`, `wcag_criteria`), 기대 `outcome`, 기대 근거 `document_id`, 정책 케이스는 기대 `PolicyAssessment`를 라벨링한다.

## 9.3. 합격선

| 지표 | 목표 |
|---|---|
| `confirmed` Finding 재현율 | ≥ 90% |
| 문제 없는 코드가 `no_issue_detected` / `no_change_needed`인 비율 | ≥ 80% |
| `improved` 케이스의 재검증 통과율 | ≥ 80% |
| 존재하지 않는 WCAG ID 또는 허위 출처 인용 | 0건 |
| WCAG 근거 연결 정확도 (매핑 정답 대비) | ≥ 80% |

첫 측정 후 조정할 수 있으며, 조정 사유는 `docs/decisions.md`에 기록한다.

---

# 10. 기술 스택

| 영역 | 기술 |
|---|---|
| Agent / Workflow | LangChain, LangGraph |
| Structured Output | Pydantic |
| Chat LLM | AWS Bedrock `us.anthropic.claude-sonnet-4-6` (`langchain-aws`의 `ChatBedrockConverse`). 모델 ID와 리전은 환경변수로 지정 (D1) |
| Backend / CLI | Python 3.11+, Typer |
| Vector DB | Chroma (Local Persistent) |
| Embeddings | AWS Bedrock `amazon.titan-embed-text-v2:0` (`langchain-aws`의 `BedrockEmbeddings`) (D2) |
| Manifest | YAML 파일 (`knowledge/manifests/`) |
| JS Runtime | Node.js 20 LTS 이상 |
| 정적 분석 | ESLint 9, eslint-plugin-jsx-a11y, @typescript-eslint/parser |
| Observability | LangSmith (D4) |
| Test / Eval | pytest |

---

# 11. 디렉터리

```text
a11y-investigator/
├── README.md
├── requirements.txt             # 고정 버전 의존성
├── pyproject.toml               # 패키지·CLI 진입점·pytest 설정
├── .env.example
├── src/a11y_investigator/
│   ├── cli.py
│   ├── config.py                # 모델·경로·한도
│   ├── agent/                   # graph.py, state.py, nodes.py, prompts.py
│   ├── chains/                  # diagnosis.py, improvement.py
│   ├── rag/                     # fetch.py, chunker.py, metadata.py, store.py, ingest.py, retriever.py
│   ├── tools/                   # input_parser.py, static_analysis.py, rule_mapping.py,
│   │                            # guideline_search.py, policy_lookup.py, code_validation.py
│   ├── schemas/                 # analyzer.py, diagnosis.py
│   └── middleware/safety.py     # 금지 패턴, 인용 검증
├── analyzer-js/
│   ├── package.json
│   └── analyze.mjs              # --type jsx|tsx, stdin → stdout JSON
├── knowledge/
│   ├── official/
│   ├── project-policies/demo-ds/   # project.yaml, *.md
│   └── manifests/                  # sources.yaml, rule-wcag-map.yaml
├── data/chroma/
├── evals/                       # datasets/, evaluate.py, reports/
├── tests/
└── docs/decisions.md
```

---

# 12. 3일 일정

### Day 1 — 정적 분석, 매핑, RAG

- 프로젝트 구성, 미결정 사항 D1·D2 결정
- Input Parser (추출, 유형 식별, 입력 제한)
- Node 분석기 (ESLint + jsx-a11y)와 Python subprocess 연동
- 규칙–WCAG 매핑 테이블
- 공식 문서 수집(6.1 범위)과 Chroma 인덱싱
- `demo-ds` 예제 정책

**완료:** React 코드에 정적 분석을 수행하고 매핑된 SC의 공식 문서를 조회할 수 있다.

### Day 2 — Workflow, 진단, 개선

- 진단 체인 (`DiagnosisOutput`)
- LangGraph 그래프 (4장)
- `decide` 판단 규칙, 수정 체인 (`FixOutput`)
- 재검증과 재수정 루프
- Guardrails (8장)
- CLI Markdown / JSON 출력, Trace 연동

**완료:** 문제가 있으면 원인과 개선된 전체 코드를 반환하고, 없으면 원본을 유지한다.

### Day 3 — 평가와 마무리

- 평가 데이터셋 19개, pytest 평가 스크립트, 합격선 측정
- Scenario C 정책 적용 테스트
- 검색 품질 개선 (정확 조회 누락, 쿼리 생성)
- 비용 측정, README 작성

**완료:** 재현 가능한 시나리오와 평가 결과를 포함한 GitHub 저장소.

---

# 13. 인수 기준

### 입력
- [ ] JSX, TSX 코드를 CLI로 입력할 수 있다.
- [ ] 코드 유형(jsx / tsx)을 식별하고, React가 아닌 코드는 `analysis_failed`로 거절한다.
- [ ] 입력 제한 초과나 코드 블록이 여러 개이면 `analysis_failed`와 사유를 반환한다.
- [ ] `--project`로 프로젝트를 지정할 수 있다.

### 진단
- [ ] 정적 분석을 수행하고 규칙을 WCAG SC에 매핑한다.
- [ ] Chroma에서 관련 표준 문서와 프로젝트 정책을 검색한다.
- [ ] 문제와 근거를 제시하고 confirmed / suspected / manual_review를 구분한다.
- [ ] 근거 없는 Finding은 `manual_review`로 강등한다.
- [ ] 존재하지 않는 WCAG ID나 전달되지 않은 문서를 인용하지 않는다.
- [ ] 프로젝트 정책 적합성을 WCAG 적합성과 별도로 보고한다.

### 개선
- [ ] 수정이 필요하면 전체 코드와 변경 이유를 출력한다.
- [ ] 5.3 기준으로 재검증하고, 린트 우회 주석이 있으면 통과시키지 않는다.
- [ ] 최대 2회 재수정하고, 초과하면 `fix_failed`로 보고한다.
- [ ] 수정이 불필요하면 원본을 유지한다.

### 기술 및 평가
- [ ] LCEL / Pydantic 구조화 출력, LangGraph 그래프, Chroma RAG
- [ ] 노드별 Trace 기록
- [ ] 보고서에 모델, 인덱스 버전, 분석기 버전 기록
- [ ] 평가 데이터셋 19개와 합격선 측정 결과를 README에 기록

---

# 14. 미결정 사항

결정 내용과 이유는 `docs/decisions.md`에 기록한다. D1·D2는 확정, D3·D4는 Phase 2 시작 전에 정한다.

**확정된 제약:** LLM과 임베딩은 교육 과정에서 제공받은 **AWS Bedrock**만 사용한다. 따라서 D1·D2는 제공받은 계정에서 **실제로 접근이 허용된 Bedrock 모델 중에서** 고른다.

**접근 확인 결과 (2026-11-18, 리전 `us-east-1`):** Converse API + 강제 Tool 호출 1회, 임베딩 1회로 직접 확인했다. 모델 목록에 보여도 호출 권한이 없는 경우가 많으므로, 아래 표에 없는 모델을 쓰려면 먼저 호출해 확인한다.

| 용도 | 호출 가능 (모델 / 추론 프로파일 ID) | 호출 불가 |
|---|---|---|
| Chat | `us.anthropic.claude-sonnet-4-6` (`global.` 도 가능), `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`, `us.amazon.nova-pro-v1:0`, `us.amazon.nova-lite-v1:0`, `us.amazon.nova-2-lite-v1:0` | Claude Sonnet 5 / 5.5, Haiku 5.5, Opus 4.5 이상, Nova Premier |
| 임베딩 | `amazon.titan-embed-text-v2:0` (1024차원) | Cohere Embed Multilingual v3, Cohere Embed v4 |

| # | 항목 | 고려사항 | 시점 |
|---|---|---|---|
| D1 | ✅ **Chat LLM: `us.anthropic.claude-sonnet-4-6`** (확정) | 진단·수정 모두 사용, temperature 0~0.2. 평가 반복 등 비용을 줄일 때는 `us.anthropic.claude-haiku-4-5-20251001-v1:0`를 보조로 사용 | 확정 (2026-11-18) |
| D2 | ✅ **임베딩: `amazon.titan-embed-text-v2:0`** (확정) | 호출 가능한 유일한 다국어 모델. 한국어·영어 문장 유사도가 0.36 정도로 높지 않으므로 공식 문서 검색은 영어 쿼리(6.5)를 유지한다. `index_version`에 모델명 포함 | 확정 (2026-11-18) |
| D3 | 실행당 비용·토큰 상한 | 예: LLM 호출 최대 6회 (진단 1 + 수정 최대 3 + 여유) | Day 2 |
| D4 | LangSmith 사용 여부 | 계정·API 키 필요. 안 쓰면 로컬 JSON Trace로 대체 | Day 2 |
