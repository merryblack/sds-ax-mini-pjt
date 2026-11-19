# 미니 PJT: A11y Investigator

## 무엇을 푸나
React 컴포넌트의 접근성 위반을 찾아도 WCAG 근거와 올바른 수정 방법을 확인하는 데 시간이 오래 걸리고 결과가 사람마다 다르다. A11y Investigator는 정적 분석과 WCAG·APG 근거 검색으로 문제를 진단하고, 재검증된 개선 코드를 돌려준다.

문서: [SERVICE.md](SERVICE.md) (서비스 정의) · [SERVICE_MVP.md](SERVICE_MVP.md) (MVP 구현 명세) · [TASKS.md](TASKS.md) (작업 목록) · [ROADMAP.md](ROADMAP.md) (장기 계획)

## 기술 스택

| 영역 | 기술 |
|---|---|
| Agent / Workflow | LangChain, LangGraph |
| Structured Output | Pydantic |
| Chat LLM | AWS Bedrock `us.anthropic.claude-sonnet-4-6` (`langchain-aws`의 `ChatBedrockConverse`). 모델 ID와 리전은 환경변수로 지정 |
| Backend / CLI | Python 3.11+, Typer |
| Vector DB | Chroma (Local Persistent) |
| Embeddings | AWS Bedrock `amazon.titan-embed-text-v2:0` (`langchain-aws`의 `BedrockEmbeddings`) |
| Manifest | YAML 파일 (`knowledge/manifests/`) |
| JS Runtime | Node.js 20 LTS 이상 |
| 정적 분석 | ESLint 9, eslint-plugin-jsx-a11y, @typescript-eslint/parser, eslint-plugin-react-hooks(재검증 전용) |
| Observability | 로컬 JSON Trace (`data/traces/`) |
| Test / Eval | pytest, RAGAS |

모델·Trace 방식 등의 선택 이유는 [docs/decisions.md](docs/decisions.md)에 기록되어 있다.

## 아키텍처

LangGraph로 구성한 고정 워크플로다. 필수 단계는 항상 실행되는 노드이고, **LLM은 진단(`diagnose`)과 수정(`generate_fix`) 두 곳에서만** 쓴다. 나머지 판단(수정 대상 결정, 인용 검증, 재검증)은 일반 코드로 처리해 결과를 재현할 수 있게 했다.

```text
입력(코드 + 요청)
  │
  ▼
parse_input ── 코드 추출, JSX/TSX 판별, 컴포넌트 힌트, 목표 레벨 결정
  ▼
analyze ────── ESLint + jsx-a11y 정적 분석 (Node)
  ▼
map_rules ──── 규칙 ID → WCAG SC / APG 패턴
  ▼
retrieve ───── 정확 조회(ID) + 영어 쿼리 벡터 검색 + 프로젝트 정책 선택 (Chroma)
  ▼
diagnose ───── [LLM] 문제 진단 → confirmed / suspected / manual_review, 정책 적합성
  ▼
decide ─────── 인용 검증·강등, 수정 대상 결정
  │ 수정 대상 없음 ─────────────────────────────┐
  ▼                                             │
generate_fix ─ [LLM] 전체 수정 코드 생성          │
  ▼                                             │
revalidate ─── 정적 재분석으로 통과 판정          │
  │ 실패 & 재시도 가능(최대 3회) → generate_fix   │
  ▼                                             ▼
report ─────── outcome 결정, 근거 URL, 요약, 재현성 정보
```

입력 추출·분석 단계나 LLM 호출이 실패하면 바로 `report`로 가서 `analysis_failed` 또는 `fix_failed`를 돌려준다.

**지식 계층**

| 컬렉션 | 내용 | 검색 방식 |
|---|---|---|
| `official` | WCAG 2.2 SC, Understanding, Techniques, WAI-ARIA APG (청크 340개) | 매핑된 SC·APG는 ID로 정확 조회, 나머지는 영어 쿼리 벡터 검색 |
| `project_policies` | 프로젝트별 정책 (`knowledge/project-policies/`) | `project_id`로 범위 제한, 관련 컴포넌트가 겹치는 정책 선택 |

## 실행 방법

### 준비물
- Python 3.11 이상 (개발 환경: 3.14)
- Node.js 20 이상 (개발 환경: 26 LTS) — 정적 분석기(ESLint + jsx-a11y) 실행용
- AWS Bedrock 접근 권한 — Chat: `us.anthropic.claude-sonnet-4-6`, 임베딩: `amazon.titan-embed-text-v2:0` ([docs/decisions.md](docs/decisions.md))
  - 리전: 현재 Chat은 `us-west-1`(`AWS_DEFAULT_REGION`), 임베딩은 `us-east-1`(`EMBEDDING_REGION`, 기본값)을 쓴다. 계정 한도·모델 제공 여부에 따라 바뀔 수 있다. 단, Titan Embed V2는 모든 리전에 있지 않으므로 임베딩 리전은 인덱스를 만든 리전과 같게 둔다.

### 1. 설치

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
cd analyzer-js; npm install; cd ..
```

### 2. 환경변수

`.env.example`을 `.env`로 복사하고 AWS 자격 증명을 채운다. `.env`는 커밋하지 않는다. 리전(`AWS_DEFAULT_REGION`, `EMBEDDING_REGION`), 모델 ID, Node 경로(`NODE_BIN`)는 선택 항목이며 설명은 `.env.example` 주석을 따른다(현재 설정이며 바뀔 수 있음).

```powershell
copy .env.example .env
```

### 3. 검색 인덱스 만들기 (최초 1회)

검색 인덱스(`data/chroma/`)는 저장소에 포함되지 않는다(`.gitignore`). 처음 받은 환경에서는 아래 명령으로 만든다. 공식 문서(`official` 컬렉션)와 프로젝트 정책(`project_policies` 컬렉션)을 함께 인덱싱하며, Bedrock 임베딩을 호출해 약 2분 걸린다.

```powershell
python -m a11y_investigator.rag.ingest
```

프로젝트 정책(`knowledge/project-policies/`)만 고쳤다면 정책만 다시 인덱싱하면 된다(수 초).

```powershell
python -m a11y_investigator.rag.ingest --policies
```

공식 문서 원본(`knowledge/official/`)은 저장소에 포함되어 있다. W3C 최신본으로 다시 받고 싶을 때만 아래를 실행한 뒤 인덱스를 다시 만든다. 출처와 커밋 해시는 `knowledge/manifests/sources.yaml`에 자동 기록된다.

```powershell
python -m a11y_investigator.rag.fetch
python -m a11y_investigator.rag.ingest
```

### 4. 테스트

```powershell
pytest                                # 기본: LLM 호출 없음 (커밋 전 전체 확인)
pytest --no-node                      # 개발 중 빠른 확인: Node 분석기 실행 테스트 제외
pytest -m llm                         # Bedrock 호출 테스트 (비용 발생)
pytest -m eval                        # 평가 실행기 1케이스 확인 (비용 발생, 전체 평가는 아래 "평가 실행")
cd analyzer-js; npm test; cd ..       # 정적 분석기 테스트
```

`-m llm` 테스트는 현재 9개, 약 2분 걸린다. 현재 계정에는 Bedrock 일일 토큰 한도가 있어 반복 실행하면 `ThrottlingException`이 날 수 있다(한도와 대응 방법은 바뀔 수 있음, [docs/decisions.md](docs/decisions.md) 참조).

### 5. 분석 실행

```powershell
a11y-investigator analyze --file examples\save_button.jsx --project demo-ds
```

| 옵션 | 설명 |
|---|---|
| `--file`, `-f` | 분석할 `.jsx` / `.tsx` 파일. 생략하면 표준 입력에서 요청 문구와 코드 블록을 함께 읽는다 |
| `--request`, `-r` | 요청 문구 (예: `"AAA 기준으로 검토해 줘"`) |
| `--project`, `-p` | 프로젝트 ID. 지정하면 해당 프로젝트 정책을 적용하고 정책 적합성을 평가한다 |
| `--level`, `-l` | 목표 레벨 `A` / `AA` / `AAA`. 생략하면 요청 문구 > 프로젝트 설정 > `AA` |
| `--json` | 사람이 읽는 Markdown 보고서 대신 `DiagnosisReport` JSON 출력 |
| `--no-trace` | Trace 파일을 남기지 않음 |

- 출력: Markdown 보고서 9개 항목(요약, 발견된 문제, 근거, 정책 적합성, 개선 필요 여부, 개선 코드, 변경 내용, 재검증, 수동 검증 항목)
- Trace: 실행마다 `data/traces/<trace_id>.json`에 노드별 시간, LLM 토큰, 예상 비용, 검색 문서, 재검증 결과가 남는다(커밋하지 않음). 경로와 요약은 표준 오류로 출력된다.
- 종료 코드: `0` 분석 완료, `1` 분석 실패(`analysis_failed`), `2` 잘못된 옵션

출력 예시 (위 명령, Scenario A 코드 + `demo-ds` 정책. 2026-11-19 실행, 일부 생략):

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

표준 오류에는 Trace 요약이 출력된다: `[trace] data\traces\<id>.json · 25.41s · tokens 9955+2259 · ≈$0.0638`

정책 없이 실행하면(Scenario A) `<button type="button">`으로 고친다. 이미 네이티브 버튼인 코드(Scenario B)는 `no_issue_detected`로 끝나고 원본을 유지한다.

Python에서 직접 실행할 수도 있다.

```python
from a11y_investigator.agent.graph import run_analysis

code = 'export default function SaveButton() {\n  return <div onClick={() => alert("saved")}>저장</div>;\n}'
report, state = run_analysis(raw_input="이 버튼 접근성 검토해 줘", file_code=code, project_id=None)
print(report.outcome)         # improved / fix_failed / no_change_needed / no_issue_detected / analysis_failed
print(report.improved_code)   # 수정된 전체 코드 (outcome이 improved / fix_failed일 때)
print(report.overall_summary)
```

### 6. 내 프로젝트 지침 추가하기

팀의 디자인 시스템 규칙이나 접근성 지침을 추가하면, Agent가 WCAG와 **별도로** 정책 적합성을 평가하고 수정 코드에도 반영한다. 정책과 WCAG가 충돌하면 WCAG를 우선하고 충돌 사실을 보고한다. 예제는 `knowledge/project-policies/demo-ds/`를 참고한다.

**1) 폴더 만들고 템플릿 복사**

```powershell
mkdir knowledge\project-policies\my-project
copy docs\policy-template\project.yaml knowledge\project-policies\my-project\
copy docs\policy-template\policy-example.md knowledge\project-policies\my-project\btn-001.md
```

**2) 파일 작성**

- `project.yaml`: `project_id`(폴더 이름과 같게), 목표 레벨, 디자인 시스템 컴포넌트 매핑
- 정책 Markdown(규칙 하나당 파일 하나): frontmatter에 `policy_id`, `project_id`, `title`, `applies_to`(button / dialog / tabs / combobox), `related_wcag`를 쓰고 본문에 규칙을 쓴다

디자인 시스템 컴포넌트를 쓰라는 정책이라면 **import할 패키지 이름(예: `@my-ds/ui`)을 본문에 적는다.** 적지 않으면 Agent는 import 경로를 지어내지 않고 네이티브 요소로 수정한다.

**3) 검증**

```powershell
a11y-investigator policies check my-project
```

형식 오류, 폴더와 다른 `project_id`, 중복 `policy_id`, 지원하지 않는 컴포넌트, 인덱스에 없는 WCAG 번호를 알려 준다.

**4) 분석**

```powershell
a11y-investigator analyze --file Component.tsx --project my-project
```

정책 파일을 고친 뒤 따로 인덱싱할 필요는 없다. `--project`로 분석할 때 정책 파일이 바뀌었으면 자동으로 다시 인덱싱한다(파일 해시를 `data/chroma/policy-hashes.json`과 비교). 수동으로 하려면 `python -m a11y_investigator.rag.ingest --policies`.

## RAGAS 평가 결과
2026-11-19 측정. 진단 단계만 측정하며, 평가 모델은 Haiku 4.5, 임베딩은 Titan V2다. 대상은 문제 있는 케이스 중 Finding이 나온 것이다(T18·T19는 14개, T20은 인-아웃 세트로 늘어 20개).

| 지표 | 1차 (T18) | 2차 (T19) | 최종 (T20, 20개) |
|---|---|---|---|
| context_recall | 0.96 | 0.96 | 0.95 |
| context_precision | 0.55 | 0.55 | 0.57 |
| faithfulness | 0.95 | 0.80 | 0.89 |
| answer_relevancy | 0.26 | 0.29 | 0.26 |

- 2차에서 faithfulness가 낮아졌다. 진단 프롬프트에 "무엇이 필수이고 무엇이 선택인지" 판단을 넣으면서 APG 필수 여부처럼 문서 발췌에 명시되지 않은 서술이 늘어난 영향으로 보인다.
- 가드레일이 제거한 인용은 1건이다(dialog-03에서 제공되지 않은 `apg-button-pattern` 인용). 최종 보고서의 허위 인용은 0건이다.
- 케이스가 14~20개뿐이고 평가 LLM 판정의 편차도 있으므로(같은 샘플이 0.2~0.6 사이로 흔들린 사례) 경향 정도로 본다.

해석
- context_recall은 높다. 정답 진단에 필요한 근거 문서가 거의 모두 검색된다.
- context_precision이 낮은 것은 검색 상한(공식 문서 6개)을 채우면서 관련이 덜한 문서도 함께 들어가기 때문이다.
- faithfulness는 검색 문서와 함께 진단 LLM이 실제로 받은 코드·정적 분석 결과를 근거로 넣어 계산했다. 검색 문서만 넣으면 코드에 대한 서술("div에 onClick만 있다")을 근거로 확인할 수 없어 점수가 0.2~0.6 사이로 흔들렸다.
- answer_relevancy는 진단 품질보다 임베딩 특성의 영향이 크다. RAGAS가 진단 결과에서 영어 질문을 만들고 이를 한국어 입력과 Titan 임베딩 유사도로 비교하는데, Titan V2는 같은 뜻의 한영 문장도 유사도가 0.36 정도다(docs/decisions.md D2). 질문을 한국어로 만들게 해도 오르지 않아(0.19) 참고 지표로만 본다.

평가 실행

```powershell
python -m evals.evaluate                     # 30개 전체 + RAGAS (약 10분, 예상 $1.6)
python -m evals.evaluate --case guardrail --no-ragas   # 카테고리(파일 이름 접두어)만
python -m evals.evaluate --case button --no-ragas
python -m evals.evaluate --from-run evals/reports/<id>.json   # 저장된 실행 결과로 재채점
```

결과는 `evals/reports/<id>.md`(요약, 커밋)와 `<id>.json`(전체 실행 기록, 커밋하지 않음)으로 저장된다.

## 인-아웃 세트 통과율 (자체 평가)
인-아웃 세트는 `evals/datasets/`의 30개 케이스다. 케이스마다 입력(요청 문구와 코드)과 기대 결과를 YAML로 라벨링했다.

**구성**

| 카테고리 | 개수 | 내용 |
|---|---|---|
| positive | 14 | 정상 진단: 문제 있는 Button·Dialog·Tabs·Combobox 코드, `demo-ds` 정책 적용 |
| negative | 8 | 문제 없는 코드 5개(바꾸지 않아야 함), 없는 프로젝트, HTML 입력, 근거 문서가 없는 패턴(Accordion) |
| edge | 4 | 코드 블록 2개, 300줄 초과, 요청 문구의 AAA 레벨, WCAG와 충돌하는 정책을 따른 코드 |
| guardrail | 4 | 코드 주석 속 프롬프트 인젝션, "완전 준수라고 써 줘", "eslint-disable로 경고만 없애 줘", 접근성과 무관한 요청(성능 최적화) |

**라벨**
- 공통: 기대 outcome
- 진단 케이스: 기대 Finding(규칙 ID, 상태, WCAG 기준), 인용해야 할 문서, 정책 판정
- 인-아웃 항목(T20)
  - 필수 항목(`traits`): 보고서·오류 사유·수동 확인 항목에 꼭 있어야 하는 것
  - 금지 표현(`forbidden`, `forbidden_in_code`): LLM이 쓴 문장과 수정 코드에 나오면 안 되는 것
  - 노드(`nodes`, `forbidden_nodes`): Trace에 실행돼야 할 노드와 실행되면 안 되는 노드. 예: 입력 거절 시 `diagnose`를 실행하지 않아야 한다.

케이스 하나는 모든 라벨을 만족해야 통과다. 합격 기준은 SERVICE.md 5장(전체 80% 이상, guardrail 100%)과 SERVICE_MVP.md 9.3의 지표 5개다.

- **최종 (2026-11-19, T20): 29 / 30 통과 (97%)** ([evals/reports/20261119-070023.md](evals/reports/20261119-070023.md))

| 카테고리 | 통과 | 목표 |
|---|---|---|
| positive | 14/14 (100%) | — |
| negative | 7/8 (88%) | — |
| edge | 4/4 (100%) | — |
| guardrail | 4/4 (100%) | 100% ✅ |
| **전체** | **29/30 (97%)** | ≥ 80% ✅ |

| 지표 (SERVICE_MVP.md 9.3) | 결과 | 목표 |
|---|---|---|
| `confirmed` Finding 재현율 | 100% | ≥ 90% ✅ |
| 문제 없는 코드가 no-change로 끝나는 비율 | 83% (5/6) | ≥ 80% ✅ |
| 수정 시도 케이스의 재검증 통과율 | 100% (21/21) | ≥ 80% ✅ |
| 허위 인용 | 0건 | 0건 ✅ |
| WCAG 근거 연결 정확도 | 100% | ≥ 80% ✅ |

  - guardrail 4건 모두 통과했다.
    - 주석 속 지시는 무시하고 정상적으로 문제를 찾아 고쳤다.
    - "완전 준수"라고 단정하지 않았다.
    - `eslint-disable`로 경고를 숨기지 않고 실제로 고쳤다.
    - 성능 최적화 요청에 `useMemo`를 넣지 않았다.
  - 입력 거절 4건(없는 프로젝트, HTML, 코드 블록 2개, 300줄 초과)은 LLM을 호출하지 않고 사유를 안내했다.
  - Accordion처럼 근거 문서가 없는 패턴은 WCAG로 확인되는 문제만 고치고, 패턴 고유 요구 사항은 수동 확인 항목으로 안내한다. 이 안내는 처음 실행에서 빠져 있어, 진단 프롬프트에 규칙 한 줄을 추가해 고쳤다.
  - 실패 1건은 combobox-03이다. 문제 없는 코드인데 목록 경계 동작(APG 선택 사항)을 다시 수정 대상으로 냈다(T19와 같은 사례).
  - no-change 비율 83%는 분모가 6개다. 문제 없는 코드 5개에 guardrail-02가 더해졌다. 기존 5개만 보면 4/5(80%)다. dialog-04는 T19 2차에서 실패했다가 이번에 통과했다. 같은 프롬프트에서도 실행마다 판단이 흔들릴 수 있는 경계 사례로 본다.

이전 측정 기록(평가 데이터셋 19개 기준)

- 1차 (2026-11-19, T18): 14 / 19 통과

| 지표 (SERVICE_MVP.md 9.3) | 1차 | 목표 |
|---|---|---|
| `confirmed` Finding 재현율 | 100% | ≥ 90% ✅ |
| 문제 없는 코드가 no-change로 끝나는 비율 | 20% (1/5) | ≥ 80% ❌ |
| 수정 시도 케이스의 재검증 통과율 | 94% (17/18) | ≥ 80% ✅ |
| 허위 인용 | 0건 | 0건 ✅ |
| WCAG 근거 연결 정확도 | 100% | ≥ 80% ✅ |

  - 실패 5건 중 4건은 문제 없는 코드를 수정한 경우다. APG의 선택 권장 사항(Home/End 키, aria-disabled 선호 등)을 `suspected`·`local`로 보고했고, decide 규칙이 이를 수정 대상으로 삼았다.
  - 나머지 1건(dialog-01)은 Escape 처리를 넣으면서 `no-static-element-interactions` 위반을 새로 만들었고, 재시도 3회 모두 해결하지 못했다.
  - 정책 판정 정확도는 100%(6/6)이고, analysis_failed는 0건이다.
- 2차 (2026-11-19, T19 개선 후): **17 / 19 통과** ([evals/reports/20261119-054203.md](evals/reports/20261119-054203.md))

| 지표 (SERVICE_MVP.md 9.3) | 1차 | 2차 | 목표 |
|---|---|---|---|
| `confirmed` Finding 재현율 | 100% | 100% | ≥ 90% ✅ |
| 문제 없는 코드가 no-change로 끝나는 비율 | 20% (1/5) | 60% (3/5) | ≥ 80% ❌ |
| 수정 시도 케이스의 재검증 통과율 | 94% (17/18) | 100% (16/16) | ≥ 80% ✅ |
| 허위 인용 | 0건 | 0건 | 0건 ✅ |
| WCAG 근거 연결 정확도 | 100% | 100% | ≥ 80% ✅ |
| (참고) 정책 판정 정확도 | 100% | 100% | — |
| (참고) RAGAS faithfulness | 0.95 | 0.80 | — |

- 개선폭: +3건
- 주요 개선 사항
  - 진단 프롬프트가 WCAG 위반·APG 필수 사항만 Finding으로 보고하고, 선택 권장 사항·다른 유효한 구현·가정에 기반한 지적은 `manual_checks`로 보낸다.
  - 수정 프롬프트가 비대화형 컨테이너에 키 핸들러를 달지 않고 Escape를 document 리스너로 처리한다. 이로써 dialog-01 `fix_failed`가 해결됐고, 재시도 없이 모두 1회차에 통과했다.
  - 정답 코드 라벨을 보강했다: dialog-04에 포커스 트랩, tabs-04에 tabpanel `tabIndex`를 넣었고, button-08 정책 판정에 `not_applicable`도 허용했다.
- 남은 미달: 문제 없는 코드 2건(combobox-03, dialog-04)을 여전히 수정했다.
  - combobox-03은 목록 경계에서의 ArrowUp 동작(APG 선택 사항)을 필수로 해석했다.
  - dialog-04는 "향후 요소가 추가되면" 같은 보강 제안을 `suspected`·`local`로 냈다.
  - 프롬프트 조정은 문제 없는 코드 5개에 과적합될 위험이 있어 여기서 멈췄고, 합격선은 낮추지 않았다(docs/decisions.md).
- 유의점: 문제 없는 코드 케이스가 5개뿐이고 이 케이스를 보며 프롬프트를 조정했으므로, 수치가 실제 일반화 성능보다 좋게 나왔을 수 있다.
- 중간 측정(20261119-053227)에서는 병렬 실행 중 Chroma 클라이언트 초기화가 경합해 2건이 실행 오류로 끝났다. 잠금을 추가해 해결했다.

## 트라이앤에러 회고

> 중요한 사례가 생길 때마다 추가한다.

**1. 한국어 정책과 영어 표준을 한 번에 검색하려던 시도**
- 시도: 사용자 요청(한국어)으로 공식 문서(영어)와 프로젝트 정책(한국어)을 모두 벡터 검색할 계획이었다.
- 실패 이유: 사용 가능한 임베딩(Titan Embed V2)에서 같은 뜻의 한국어·영어 문장 유사도가 약 0.36으로 낮았다.
- 채택: 공식 문서는 규칙 ID·정적 분석 메시지로 만든 **영어 템플릿 쿼리**와 **ID 정확 조회**로 찾고, 정책은 벡터 검색 대신 **관련 컴포넌트가 겹치는 정책을 선택**한다. LLM 호출 없이 검색 품질을 확보했다.

**2. "린트 통과 = 올바른 수정"이라는 가정**
- 시도: 수정 코드를 jsx-a11y로만 다시 검사했다.
- 실패 이유: ① Dialog의 Escape 처리를 `role="dialog"` div에 `onKeyDown`으로 넣어 새 위반이 생겼고, ② 재시도 결과는 접근성 검사는 통과했지만 `useEffect`를 early return 뒤에 넣어 **React Hooks 규칙을 어긴 깨진 코드**였다.
- 채택: 재검증을 "원본 대비 위반 증가 없음"으로 판정하고 실패 사유를 피드백으로 넘겨 재시도(최대 3회)하게 했다. 접근성과 무관한 기능 회귀를 막기 위해 `react-hooks/rules-of-hooks`를 **재검증 전용 규칙**으로 추가했다.
- 남은 한계: Hooks 외의 기능 회귀(로직 변경, 스타일 누락 등)는 정적 분석으로 잡지 못한다. 테스트 실행·브라우저 검증은 ROADMAP V0.6에서 다룬다.

**3. "문제를 많이 찾을수록 좋다"는 진단 방향**
- 시도: 진단 LLM에게 APG 문서를 근거로 주고, 근거를 인용한 `suspected` Finding 중 범위가 `local`이면 자동으로 수정하게 했다.
- 실패 이유: 1차 평가에서 문제 없는 코드 5개 중 4개를 "개선"했다. Home/End 키, `aria-disabled` 선호처럼 APG의 선택 권장 사항이나 다른 유효한 구현을 위반처럼 보고했고, 근거 문서가 붙어 있어 가드레일도 통과했다.
- 채택: 자동 수정 대상은 "WCAG 실패 또는 APG 필수 사항"으로 좁히고, 선택 권장·대안 구현·가정에 기반한 지적은 수동 확인 항목으로 보냈다. no-change 비율이 20%에서 60%로 올랐다.
- 남은 한계: 무엇이 필수인지는 여전히 LLM 판단이다. 평가 2건이 아직 미달이다. 근거 문서의 "optional" 표기를 메타데이터로 만들거나, 수정 전에 `suspected` Finding을 한 번 더 검증하는 단계를 두는 방안을 V0.3에서 검토한다.

## 출처와 라이선스

`knowledge/official/`의 WCAG 2.2, Understanding WCAG, Techniques for WCAG, WAI-ARIA Authoring Practices Guide 문서는 W3C의 저작물이며 [W3C Software and Document License](https://www.w3.org/copyright/software-license/)에 따라 포함했다. 수집한 원본 URL과 GitHub 커밋 해시(`w3c/wcag`, `w3c/aria-practices`)는 [knowledge/manifests/sources.yaml](knowledge/manifests/sources.yaml)에 기록되어 있다. 진단 보고서는 인용한 문서마다 W3C 원문 URL을 함께 표시한다.

## 핵심 코드 위치

> 현재 MVP(Phase 0~3, T01~T19) 완료 기준이며, 이후 버전에서 바뀔 수 있다. ✅ 구현됨 (Task별 내역은 [TASKS.md](TASKS.md) 참조)

```text
mini-project/
├── src/a11y_investigator/
│   ├── cli.py                  ✅ CLI 진입점 `a11y-investigator` (analyze, policies check)
│   ├── config.py               ✅ 모델 ID·경로·한도 설정
│   ├── report_markdown.py      ✅ 보고서 Markdown 렌더링 (9개 항목)
│   ├── agent/
│   │   ├── state.py            ✅ LangGraph 상태
│   │   ├── trace.py            ✅ 로컬 JSON Trace (노드 시간, 토큰, 예상 비용)
│   │   ├── decision.py         ✅ decide: 인용 검증 적용 + 수정 대상 결정 (일반 코드)
│   │   ├── graph.py            ✅ 메인 에이전트 그래프, 보고서 조립, run_analysis() 진입점
│   │   ├── nodes.py            ✅ 8개 노드와 분기 조건 (report 노드는 graph.py)
│   │   └── prompts.py          ✅ 진단·수정 프롬프트
│   ├── chains/
│   │   ├── llm.py              ✅ Bedrock Claude 모델 생성
│   │   ├── diagnosis.py        ✅ 진단 체인 (구조화 출력 → DiagnosisOutput)
│   │   └── improvement.py      ✅ 수정 체인 (구조화 출력 → FixOutput, 재시도 피드백)
│   ├── tools/
│   │   ├── input_parser.py     ✅ 코드 추출, JSX/TSX 판별, 컴포넌트 힌트
│   │   ├── static_analysis.py  ✅ Node 정적 분석기 호출
│   │   ├── rule_mapping.py     ✅ 규칙 → WCAG SC / APG 매핑
│   │   ├── guideline_search.py ✅ WCAG 기준 조회, 공식 문서 검색
│   │   ├── policy_lookup.py    ✅ 프로젝트 정책 로딩·검증
│   │   └── code_validation.py  ✅ 수정 코드 재검증 (통과 기준 4개, 재시도 피드백)
│   ├── rag/
│   │   ├── fetch.py            ✅ W3C 문서 수집
│   │   ├── chunker.py          ✅ 문서 유형별 청킹
│   │   ├── metadata.py         ✅ 청크 메타데이터
│   │   ├── store.py            ✅ Titan 임베딩 + Chroma
│   │   ├── ingest.py           ✅ 인덱싱
│   │   └── retriever.py        ✅ 정확 조회 + 벡터 검색 + 정책 선택
│   ├── schemas/                ✅ 정적 분석·근거·진단·보고서 스키마
│   └── middleware/safety.py    ✅ 인용 검증·강등, 린트 우회 주석 차단
├── analyzer-js/analyze.mjs     ✅ ESLint 9 + jsx-a11y 정적 분석기, 재검증용 rules-of-hooks (stdin → JSON)
├── knowledge/
│   ├── official/               ✅ WCAG·Understanding·Techniques·APG 원문 (W3C)
│   ├── project-policies/       ✅ 프로젝트 정책 (예제: demo-ds)
│   └── manifests/              ✅ 규칙–WCAG 매핑, 문서 출처·커밋 해시
├── docs/
│   ├── decisions.md            ✅ 모델 선택 등 결정 기록
│   └── policy-template/        ✅ 내 프로젝트 지침 템플릿
├── examples/                   ✅ 실행 예시 컴포넌트
├── evals/                      ✅ 인-아웃 세트 30개(datasets/), 실행기(evaluate.py), 지표(metrics.py), RAGAS(ragas_eval.py), 리포트(reports/)
├── tests/                      ✅ pytest (LLM 호출 없는 기본 테스트 + `-m llm`), 공용 샘플·가짜 객체는 samples.py·fakes.py
└── data/                       생성물, 커밋하지 않음
    ├── chroma/                 검색 인덱스, policy-hashes.json
    └── traces/                 실행별 Trace JSON
```