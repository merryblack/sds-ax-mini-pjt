# 사용 가이드

[README](../README.md)의 "실행 방법"을 자세히 설명한다. 설치와 인덱스 생성은 README를 먼저 따른다.

모든 명령은 저장소 폴더에서 `python a11y.py ...`로 실행한다. OS·셸에 상관없이 같고, 가상환경을 활성화할 필요가 없다. 가상환경을 활성화했다면 `python a11y.py` 대신 `a11y-investigator`를 써도 된다. macOS·Linux에서는 `python` 대신 `python3`일 수 있다.

- [1. 분석 실행](#1-분석-실행)
- [2. 검색 인덱스 관리](#2-검색-인덱스-관리)
- [3. 프로젝트 지침 관리](#3-프로젝트-지침-관리)

---

## 1. 분석 실행

### 명령과 옵션

```text
python a11y.py analyze --file examples/save_button.jsx --project demo-ds
```

| 옵션 | 설명 |
|---|---|
| `--file`, `-f` | 분석할 `.jsx` / `.tsx` 파일. 생략하면 표준 입력에서 요청 문구와 코드 블록을 함께 읽는다 |
| `--request`, `-r` | 요청 문구 (예: `"AAA 기준으로 검토해 줘"`) |
| `--project`, `-p` | 프로젝트 ID. 지정하면 해당 프로젝트 정책을 적용하고 정책 적합성을 평가한다 |
| `--level`, `-l` | 목표 레벨 `A` / `AA` / `AAA`. 생략하면 요청 문구 > 프로젝트 설정 > `AA` |
| `--json` | 사람이 읽는 Markdown 보고서 대신 `DiagnosisReport` JSON 출력 |
| `--no-trace` | Trace 파일을 남기지 않음 |

입력 규칙(SERVICE_MVP.md 2장)
- 지원 입력은 React JSX / TSX이다. HTML 등은 `analysis_failed`로 거절한다.
- 코드는 300줄 또는 약 8,000 토큰까지 받는다.
- 코드 블록은 한 번에 하나만 받는다. 넘으면 분석하지 않고 사유를 안내한다.

### 출력

**보고서:** Markdown 9개 항목으로 나온다.
1. 요약
2. 발견된 문제
3. 근거
4. 정책 적합성
5. 개선 필요 여부
6. 개선 코드
7. 변경 내용
8. 재검증
9. 수동 검증 항목

**outcome**

| 값 | 의미 |
|---|---|
| `improved` | 수정했고 재검증을 통과했다 |
| `fix_failed` | 3회 시도에도 재검증을 통과하지 못했다. 검증되지 않은 코드라는 경고와 함께 출력한다 |
| `no_change_needed` | 문제는 있지만 자동 수정 대상이 아니다. 구조적 수정, 수동 확인 등이 해당한다 |
| `no_issue_detected` | 자동 검사 범위에서 문제를 찾지 못했다 |
| `analysis_failed` | 입력 거절이나 실행 오류. 사유를 함께 출력한다 |

**종료 코드:** `0` 분석 완료, `1` 분석 실패(`analysis_failed`), `2` 잘못된 옵션

**Trace**
- 실행마다 `data/traces/<trace_id>.json`이 남는다(커밋하지 않음).
- 기록 내용: 노드별 실행 시간, LLM 토큰과 예상 비용, 검색 쿼리와 문서(`retrieval.official`, `retrieval.policies`), 재검증 결과, 경고와 오류
- 경로와 요약은 표준 오류로 출력된다.

```text
[trace] data\traces\<id>.json · 25.41s · tokens 9955+2259 · ≈$0.0638
```

### 출력 예시

위 명령으로 Scenario A 코드에 `demo-ds` 정책을 적용한 결과다(2026-11-19 실행, 일부 생략).

````markdown
## 1. 요약
문제 2건(확정 2, 추정 0, 수동 확인 0). 수정 대상 2건을 고쳤고 재검증을 통과했습니다(시도 1회, 변경 3줄).
자동 검사(정적 분석·문서 근거) 범위 안의 결과이며, 접근성 완전 준수를 의미하지 않습니다.

## 2. 발견된 문제
### F1. 키보드로 접근·조작 불가능한 클릭 핸들러 (2.1.1)
- 상태: **확정** · 심각도: critical · 수정 대상 · 위치: L2
### F2. 인터랙티브 역할 및 접근 가능한 이름 누락 (4.1.2)

## 3. 근거
| F1 | 정적 분석 | `jsx-a11y/click-events-have-key-events` | line 2 |
| F1 | 문서 | `wcag-2.1.1` | https://www.w3.org/TR/WCAG22/#keyboard |
| F2 | 문서 | `apg-button-roles` | https://www.w3.org/WAI/ARIA/apg/patterns/button/#roles_states_properties |

## 4. 프로젝트 정책 적합성
| `demo-ds-btn-001` | 위반 | ... `<div onClick>` 대신 `@demo-ds/ui`의 `<Button>`을 써야 합니다. |
| `demo-ds-icon-001` | 해당 없음 | 텍스트를 표시하는 버튼이라 적용되지 않습니다. |
| `demo-ds-focus-001` | WCAG와 충돌 (WCAG 우선) | `outline: none` 정책은 WCAG 2.4.7 Focus Visible과 충돌합니다. ... |

## 6. 개선 코드
```jsx
import { Button } from "@demo-ds/ui";

export default function SaveButton() {
  return <Button onClick={() => alert("saved")}>저장</Button>;
}
```

## 8. 재검증 결과
- 결과: **통과** (시도 1회, 변경 3줄)
- 정적 분석 위반: 2건 → 0건

## 9. 수동 검증 필요 항목
- 포커스 아웃라인 가시성 확인 ... (WCAG 2.4.7)
- 스크린 리더에서 버튼 역할과 이름('저장')이 올바르게 읽히는지 확인
````

정책 없이 실행하면(Scenario A) `<button type="button">`으로 고친다. 이미 네이티브 버튼인 코드(Scenario B)는 `no_issue_detected`로 끝나고 원본을 유지한다.

### Python에서 실행

```python
from a11y_investigator.agent.graph import run_analysis

code = 'export default function SaveButton() {\n  return <div onClick={() => alert("saved")}>저장</div>;\n}'
report, state = run_analysis(raw_input="이 버튼 접근성 검토해 줘", file_code=code, project_id=None)
print(report.outcome)         # improved / fix_failed / no_change_needed / no_issue_detected / analysis_failed
print(report.improved_code)   # 수정된 전체 코드 (outcome이 improved / fix_failed일 때)
print(report.overall_summary)
```

`tracer=Tracer()`(`a11y_investigator.agent.trace`)를 넘기면 CLI와 같은 Trace를 만들 수 있다.

---

## 2. 검색 인덱스 관리

| 상황 | 명령 | 소요 |
|---|---|---|
| 처음 설치 | `python setup_env.py --yes` (또는 `python a11y.py index`) | 약 2분 (Bedrock 임베딩) |
| 프로젝트 정책만 수동 반영 | `python a11y.py index --policies` | 수 초 |
| W3C 원문을 최신본으로 갱신 | `python a11y.py fetch` 후 `python a11y.py index` | 수 분 |

- 인덱스(`data/chroma/`)는 저장소에 포함되지 않는다. 공식 문서 원본(`knowledge/official/`)은 포함되어 있다.
- 원문을 갱신하면 출처와 커밋 해시가 `knowledge/manifests/sources.yaml`에 기록된다.
- 임베딩 모델을 바꾸면 전체 인덱스를 다시 만들어야 한다(docs/decisions.md D2).

---

## 3. 프로젝트 지침 관리

팀의 디자인 시스템 규칙이나 접근성 지침을 추가하면, Agent가 WCAG와 **별도로** 정책 적합성을 평가하고 수정 코드에도 반영한다. 정책과 WCAG가 충돌하면 WCAG를 우선하고 충돌 사실(`conflict_with_wcag`)을 보고한다.

판단 기준이 바뀌었을 때의 흐름은 다음과 같다.

1. 수정
2. 검증
3. 반영(자동)
4. 반영 확인
5. 회귀 테스트로 남기기

### 3.1. 파일 구조

```text
knowledge/project-policies/<project_id>/
├── project.yaml        # 프로젝트 설정: target_level, component_mapping
├── btn-001.md          # 정책 하나당 파일 하나 (파일 이름은 자유)
└── ...
```

예제는 시연용 `knowledge/project-policies/demo-ds/`이고, 템플릿은 `docs/policy-template/`에 있다.

새 프로젝트를 만들 때는 다음 명령으로 템플릿을 복사한다.

```powershell
mkdir knowledge\project-policies\my-project
copy docs\policy-template\project.yaml knowledge\project-policies\my-project\
copy docs\policy-template\policy-example.md knowledge\project-policies\my-project\btn-001.md
```

### 3.2. 정책 작성·수정

```markdown
---
policy_id: my-project-btn-002    # 프로젝트 안에서 고유. 기존 정책 수정이면 그대로 둔다
project_id: my-project           # 폴더 이름과 같아야 한다
title: 위험 동작 버튼에는 확인 대화상자를 연결한다
applies_to: [button]             # button | dialog | tabs | combobox 중에서만
related_wcag: ["3.3.4"]          # 인덱스에 있는 SC만
---
본문: 무엇을 해야 하고 무엇을 하면 안 되는지 구체적으로 쓴다.
```

**본문 작성 요령**
- **판단 가능한 문장으로 쓴다:** "~를 사용한다", "~를 금지한다"처럼 쓴다. 모호하면 `not_applicable`로 빠지기 쉽다.
- **패키지 이름을 적는다:** 디자인 시스템 컴포넌트를 요구한다면 import할 패키지 이름(예: `@my-ds/ui`의 `<Button>`)을 반드시 적는다. 적지 않으면 Agent는 import 경로를 지어내지 않고 네이티브 요소로 고친다.
- **코드 예시를 넣는다:** 한 줄이라도 넣으면 수정 코드에 그대로 반영될 가능성이 높다.
- **정책 하나에 규칙 하나:** 한 파일에는 규칙 하나만 넣는다. 검색과 판정이 정책 하나를 단위로 처리한다.
- **삭제는 파일을 지우면 된다:** 다음 분석 때 인덱스에서도 빠진다.

**`project.yaml`**
- `target_level`: 프로젝트 기준 레벨(예: AA → AAA). 실제 적용 순서는 `--level` 옵션, 요청 문구, 이 설정 순이다.
- `component_mapping`: 디자인 시스템 컴포넌트를 네이티브 요소로 매핑한다(예: `Button: button`). 정적 분석기가 그 컴포넌트를 해당 요소처럼 검사한다.

### 3.3. 검증 (LLM 호출 없음)

```text
python a11y.py policies check my-project
```

다음 문제를 한 번에 모두 출력하고, 문제가 있으면 종료 코드 1로 끝난다.
- frontmatter 누락
- 폴더와 다른 `project_id`
- 중복 `policy_id`
- 지원하지 않는 `applies_to`
- 인덱스에 없는 WCAG 번호

### 3.4. 반영 (자동 재인덱싱)

따로 할 일은 없다. `--project`로 분석하면 정책 파일 해시를 `data/chroma/policy-hashes.json`과 비교한다. 바뀐 내용이 있으면 해당 프로젝트 정책만 지우고 다시 인덱싱하며, 추가·수정·삭제가 모두 반영된다. 미리 반영하려면 `python a11y.py index --policies`를 실행한다.

### 3.5. 반영 확인 (한 건씩 테스트)

테스트 코드는 세 가지를 준비한다. ①만 확인하면 정책을 지키는 코드까지 고쳐 버리는 문제를 놓친다.

| 테스트 코드 | 기대 결과 |
|---|---|
| ① 새 정책을 **어기는** 코드 | 정책 판정 `violated`, 수정 코드가 정책을 따름 |
| ② 새 정책을 **지키는** 코드 | 정책 판정 `compliant`, 정책 때문에 수정하지 않음 |
| ③ 정책과 **무관한** 컴포넌트 | 정책이 검색되지 않거나 `not_applicable` |

```text
python a11y.py analyze --file test/violating.jsx --project my-project
```

**확인할 곳**
1. **정책이 LLM에 전달됐는지 (Trace)**
   - `retrieval.policies`에 새 `policy_id`가 있어야 한다.
   - 파일을 고친 직후 첫 실행이면 `retrieval.policies_reindexed`가 `true`다.
2. **판정:** 보고서 **4. 프로젝트 정책 적합성** 표의 결과와 설명
3. **수정 반영:** **6. 개선 코드**가 정책을 따르는지, **8. 재검증 결과**가 통과인지
4. **판단 근거:** **3. 근거** 표에 정책 ID(`project_policy`)가 인용됐는지

`--json`을 붙이면 `policy_assessments`를 스크립트로 바로 확인할 수 있다.

**결과가 기대와 다를 때**

| 증상 | 확인할 것 |
|---|---|
| Trace의 `retrieval.policies`에 새 정책이 없다 | `applies_to`가 테스트 코드의 컴포넌트와 맞는지 확인한다. 정책은 **컴포넌트 유형이 겹치는 것만** 선택된다. 아래 한계 1·3번도 확인한다 |
| 정책은 전달됐는데 판정이 이상하다 | 본문이 판단 가능한 문장인지 확인한다 |
| 수정 코드가 정책 컴포넌트 대신 네이티브 요소를 쓴다 | 본문에 패키지 이름이 있는지, `component_mapping`에 등록됐는지 확인한다 |
| `conflict_with_wcag`가 나오고 정책이 적용되지 않는다 | 정상 동작이다. WCAG를 우선한다(예: `demo-ds-focus-001`의 outline 제거) |

### 3.6. 회귀 테스트로 남기기

확인한 정책은 평가 케이스로 남겨 두면, 프롬프트나 다른 정책이 바뀌어도 계속 확인할 수 있다. 케이스 형식은 [evaluation.md](evaluation.md)를 참고한다.

```yaml
# evals/datasets/policy-my-project-btn-002-violation.yaml
id: policy-my-project-btn-002-violation
category: positive
kind: policy
component: button
code_type: jsx
project_id: my-project
request: 우리 지침 기준으로 삭제 버튼 검토해 줘.
code: |
  ...정책을 어기는 코드...
expected:
  outcomes: [improved]
  static_rule_ids: [...]          # 분석기 결과와 정확히 같아야 한다
  findings: [...]
  document_ids: [...]
  policy_assessments:              # 해당 컴포넌트에 적용되는 정책을 모두 적는다
    - policy_id: my-project-btn-002
      status: violated
  forbidden_in_code: ["<button"]   # 예: 네이티브 버튼을 쓰면 실패
```

다음 명령으로 이 케이스만 실행한다.

```text
python a11y.py eval --case policy-my-project --no-ragas
```

- `tests/test_eval_dataset.py`가 케이스 수(현재 30개)를 고정하고 있어, 케이스를 추가하면 이 테스트도 함께 고친다.
- `demo-ds`에 정책을 추가하면 기존 평가 케이스의 정책 라벨(해당 컴포넌트의 정책을 모두 적어야 함)이 맞지 않게 된다. 실험할 때는 `demo-ds`를 복사한 **별도 프로젝트**를 쓰는 편이 안전하다.

### 3.7. 한계 (현재 구현)

1. **컴포넌트당 정책은 최대 4개까지만 LLM에 전달된다.**
   - `applies_to` 개수가 적은 구체적인 정책이 먼저 선택된다.
   - 예를 들어 button 정책이 5개 이상이면 여러 컴포넌트에 걸친 범용 정책부터 빠지고, 보고서에는 따로 표시되지 않는다. **Trace의 `retrieval.policies`로 확인한다.**
2. **`applies_to`는 button, dialog, tabs, combobox 4종만 지원한다.**
3. **코드에서 컴포넌트 유형을 찾지 못하면 정책 선택 방식이 바뀐다.**
   - 이때는 벡터 검색으로 정책을 고른다. 검색 쿼리가 영어 템플릿이라 한국어 정책이 잘 잡히지 않을 수 있다.
   - 테스트 코드에 `role` 속성이나 `Button`·`Dialog` 같은 이름이 드러나게 한다.
4. **정책 판정은 LLM 판단이다.** 실행마다 흔들릴 수 있으므로 중요한 정책은 2~3회 실행해 일관성을 본다. 1회 비용은 약 $0.06이다.
5. **정책으로 WCAG 기준을 낮출 수는 없다.** 충돌하면 WCAG를 우선한다.
