# 미니 PJT: A11y Investigator

## 무엇을 푸나
웹 React 컴포넌트의 접근성 위반을 찾아도 WCAG 근거와 올바른 수정 방법을 확인하는 데 시간이 오래 걸리고 결과가 사람마다 다르다. A11y Investigator는 정적 분석과 WCAG·APG 근거 검색으로 문제를 진단하고, 재검증된 개선 코드를 돌려준다. 대상은 **웹(React DOM)**이며, React Native와 모바일 네이티브 앱은 다루지 않는다.

| 문서 | 내용 |
|---|---|
| [docs/guide.md](docs/guide.md) | 사용 가이드: 분석 실행 상세, 인덱스 관리, 프로젝트 지침 관리 |
| [docs/evaluation.md](docs/evaluation.md) | 평가 리포트: 인-아웃 세트, 결과, RAGAS, 측정 기록 |
| [docs/decisions.md](docs/decisions.md) | 모델·Trace 방식 등 결정 기록, 사용량 |
| [SERVICE.md](SERVICE.md) · [SERVICE_MVP.md](SERVICE_MVP.md) | 서비스 정의 · MVP 구현 명세 |
| [TASKS.md](TASKS.md) · [ROADMAP.md](ROADMAP.md) | 작업 목록 · 장기 계획 |

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
  │ 실패 & 재시도 가능(최대 2회) → generate_fix   │
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

어떤 OS·셸(PowerShell, cmd, Git Bash, macOS·Linux 터미널)에서도 **같은 명령**으로 설치하고 실행한다. 가상환경을 직접 활성화할 필요가 없다.

> macOS·Linux에서 `python` 명령이 없으면 `python3`로 바꿔 입력한다. Windows에서는 `py`도 된다.

### 준비물
- Python 3.11 이상 (개발 환경: 3.14)
- Node.js 20 이상 (개발 환경: 26 LTS) — 정적 분석기(ESLint + jsx-a11y) 실행용
- AWS Bedrock 접근 권한
  - 모델: Chat `us.anthropic.claude-sonnet-4-6`, 임베딩 `amazon.titan-embed-text-v2:0`
  - 리전: 현재 Chat은 `us-west-1`, 임베딩은 `us-east-1`이며 바뀔 수 있다([docs/decisions.md](docs/decisions.md))

### 1. 설치

저장소 폴더에서 실행한다.

```text
python setup_env.py
```

설치 스크립트가 하는 일(여러 번 실행해도 되며, 끝난 단계는 건너뛴다):
1. Python·Node.js 버전을 확인한다.
2. `.venv`를 만들고 Python 의존성을 설치한다.
3. 정적 분석기(`analyzer-js`) 의존성을 설치한다.
4. `.env`가 없으면 `.env.example`을 복사해 만든다.
5. AWS 키가 입력되어 있으면 검색 인덱스를 만든다(3번 참고).

### 2. 환경변수

1번이 만든 `.env`에 AWS 자격 증명(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)을 채운다(`.env`는 커밋하지 않음). 리전·모델 ID·Node 경로는 선택 항목이며 `.env.example` 주석을 따른다.

### 3. 검색 인덱스 만들기 (최초 1회)

키를 채운 뒤 설치 스크립트를 한 번 더 실행하면, 확인을 거쳐 검색 인덱스(`data/chroma/`)를 만든다. Bedrock 임베딩을 호출해 약 2분 걸린다. 질문 없이 진행하려면 `--yes`를 붙인다.

```text
python setup_env.py --yes
```

인덱스는 저장소에 포함되지 않는다. 정책만 다시 인덱싱하거나 W3C 원문을 갱신하는 방법은 [사용 가이드 2장](docs/guide.md#2-검색-인덱스-관리)에 있다.

### 4. 테스트

개발자용이다. 저장소 폴더에서 실행한다.

```text
python a11y.py test              # 기본: LLM 호출 없음 (커밋 전 전체 확인)
python a11y.py test --no-node    # 빠른 확인: Node 분석기 실행 테스트 제외
python a11y.py test -m llm       # Bedrock 호출 테스트 11개 (비용 발생, 약 2~3분)
```

`python a11y.py test` 뒤의 인자는 pytest에 그대로 전달된다. 정적 분석기 테스트는 `analyzer-js` 폴더에서 `npm test`로 실행한다. 계정에 Bedrock 일일 토큰 한도가 있어 반복 실행하면 `ThrottlingException`이 날 수 있다(현재 기준이며 바뀔 수 있음).

### 5. 분석 실행

```text
python a11y.py analyze --file examples/save_button.jsx --project demo-ds
```

- 출력: 요약, 발견된 문제, 근거(W3C 원문 URL), 정책 적합성, 개선 코드, 재검증 결과 등 Markdown 보고서 9개 항목. `--json`이면 JSON으로 출력한다.
- 예시 결과: `<div onClick>`을 `demo-ds` 정책대로 `@demo-ds/ui`의 `<Button>`으로 고치고 재검증을 통과한다. 정책 없이 실행하면 `<button type="button">`으로 고친다.
- 실행마다 `data/traces/`에 Trace(노드별 시간, 토큰, 예상 비용, 검색 문서)가 남는다.
- Bedrock을 호출한다. 1회 약 25초, 약 $0.06이다(현재 기준).
- `a11y.py`는 가상환경의 CLI를 대신 실행하는 런처다. 가상환경을 활성화했다면 `a11y-investigator analyze ...`로 바로 써도 된다.

옵션 전체, 출력 예시, outcome 종류, Python에서 실행하는 방법은 [사용 가이드 1장](docs/guide.md#1-분석-실행)을 참고한다. `examples/`에는 드롭다운, 모달, 상품 카드, 탭, 검색 자동완성, 아이콘 툴바, 로그인 폼 예시가 더 있다(목록은 [사용 가이드 1장](docs/guide.md#예시-컴포넌트)).

### 6. 내 프로젝트 지침 추가하기

팀의 디자인 시스템 규칙이나 접근성 지침을 `knowledge/project-policies/<project_id>/`에 정책 파일(규칙 하나당 Markdown 하나)로 추가하면, Agent가 WCAG와 **별도로** 정책 적합성을 평가하고 수정 코드에도 반영한다. WCAG와 충돌하는 정책은 WCAG를 우선하고 충돌을 보고한다.

```text
python a11y.py policies init my-project             # 템플릿으로 새 프로젝트 폴더 생성 + 검증
python a11y.py policies check my-project            # 정책을 고친 뒤 형식 검증 (LLM 호출 없음)
python a11y.py analyze --file Component.tsx --project my-project
```

정책 파일이 바뀌면 다음 분석 때 자동으로 다시 인덱싱한다. 정책 작성 요령, 반영 확인 방법(Trace·보고서에서 볼 곳), 회귀 테스트로 남기는 법, 현재 한계는 [사용 가이드 3장](docs/guide.md#3-프로젝트-지침-관리)에 있다.

## RAGAS 평가 결과

진단 단계의 검색 근거와 설명 품질을 측정했다(2026-11-19 최종, 대상 20개, 평가 모델 Haiku 4.5).

| context_recall | context_precision | faithfulness | answer_relevancy |
|---|---|---|---|
| 0.95 | 0.57 | 0.89 | 0.26 |

근거 검색(recall)과 근거 기반 서술(faithfulness)은 높다. precision은 검색 상한을 채우며 덜 관련된 문서가 섞여 낮다. answer_relevancy는 Titan 임베딩의 한영 유사도 한계 때문에 낮게 나오는 참고 지표다. 회차별 수치와 해석은 [평가 리포트 3장](docs/evaluation.md#3-ragas)에 있다.

## 인-아웃 세트 통과율 (자체 평가)

`evals/datasets/`의 30개 케이스로 측정했다. 구성은 positive 14, negative 8, edge 4, guardrail 4다.

| 카테고리 | positive | negative | edge | guardrail | **전체** |
|---|---|---|---|---|---|
| 통과 | 14/14 | 7/8 | 4/4 | 4/4 ✅ | **29/30 (97%)** ✅ |

합격 기준은 전체 80% 이상, guardrail 100%다(SERVICE.md).

| 지표 (SERVICE_MVP.md 9.3) | 결과 | 목표 |
|---|---|---|
| `confirmed` Finding 재현율 | 100% | ≥ 90% |
| 문제 없는 코드를 그대로 두는 비율 | 83% | ≥ 80% |
| 수정 코드의 재검증 통과율 | 100% | ≥ 80% |
| 허위 인용 | 0건 | 0건 |
| WCAG 근거 연결 정확도 | 100% | ≥ 80% |

- 측정 추이: 14/19(T18) → 17/19(T19) → 29/30(T20, 세트 확장). 문제 없는 코드를 고쳐 버리는 오탐을 줄인 것이 가장 큰 개선이다(회고 3번).
- 케이스 구성, 라벨, 실패 분석, 회차별 기록, 평가 실행 방법은 [평가 리포트](docs/evaluation.md)에 있다.

## 트라이앤에러 회고

> 중요한 사례가 생길 때마다 추가한다.

**1. 한국어 정책과 영어 표준을 한 번에 검색하려던 시도**
- 시도: 사용자 요청(한국어)으로 공식 문서(영어)와 프로젝트 정책(한국어)을 모두 벡터 검색할 계획이었다.
- 실패 이유: 사용 가능한 임베딩(Titan Embed V2)에서 같은 뜻의 한국어·영어 문장 유사도가 약 0.36으로 낮았다.
- 채택: 공식 문서는 규칙 ID·정적 분석 메시지로 만든 **영어 템플릿 쿼리**와 **ID 정확 조회**로 찾고, 정책은 벡터 검색 대신 **관련 컴포넌트가 겹치는 정책을 선택**한다. LLM 호출 없이 검색 품질을 확보했다.

**2. "린트 통과 = 올바른 수정"이라는 가정**
- 시도: 수정 코드를 jsx-a11y로만 다시 검사했다.
- 실패 이유: ① Dialog의 Escape 처리를 `role="dialog"` div에 `onKeyDown`으로 넣어 새 위반이 생겼고, ② 재시도 결과는 접근성 검사는 통과했지만 `useEffect`를 early return 뒤에 넣어 **React Hooks 규칙을 어긴 깨진 코드**였다.
- 채택: 재검증을 "원본 대비 위반 증가 없음"으로 판정하고 실패 사유를 피드백으로 넘겨 최대 2회 재시도(총 3회 시도)하게 했다. 접근성과 무관한 기능 회귀를 막기 위해 `react-hooks/rules-of-hooks`를 **재검증 전용 규칙**으로 추가했다.
- 남은 한계: Hooks 외의 기능 회귀(로직 변경, 스타일 누락 등)는 정적 분석으로 잡지 못한다. 테스트 실행·브라우저 검증은 ROADMAP V0.6에서 다룬다.

**3. "문제를 많이 찾을수록 좋다"는 진단 방향**
- 시도: 진단 LLM에게 APG 문서를 근거로 주고, 근거를 인용한 `suspected` Finding 중 범위가 `local`이면 자동으로 수정하게 했다.
- 실패 이유: 1차 평가에서 문제 없는 코드 5개 중 4개를 "개선"했다. Home/End 키, `aria-disabled` 선호처럼 APG의 선택 권장 사항이나 다른 유효한 구현을 위반처럼 보고했고, 근거 문서가 붙어 있어 가드레일도 통과했다.
- 채택: 자동 수정 대상은 "WCAG 실패 또는 APG 필수 사항"으로 좁히고, 선택 권장·대안 구현·가정에 기반한 지적은 수동 확인 항목으로 보냈다. no-change 비율이 20%에서 60%로 올랐고, 세트를 확장한 최종 측정에서는 83%로 합격선을 넘었다.
- 남은 한계: 무엇이 필수인지는 여전히 LLM 판단이다. 최종 측정에서도 문제 없는 코드 1건(combobox-03)을 고쳤고, 경계 사례는 실행마다 판단이 흔들린다. 근거 문서의 "optional" 표기를 메타데이터로 만들거나, 수정 전에 `suspected` Finding을 한 번 더 검증하는 단계를 두는 방안을 V0.3에서 검토한다.

## 출처와 라이선스

`knowledge/official/`의 WCAG 2.2, Understanding WCAG, Techniques for WCAG, WAI-ARIA Authoring Practices Guide 문서는 W3C의 저작물이며 [W3C Software and Document License](https://www.w3.org/copyright/software-license/)에 따라 포함했다. 수집한 원본 URL과 GitHub 커밋 해시(`w3c/wcag`, `w3c/aria-practices`)는 [knowledge/manifests/sources.yaml](knowledge/manifests/sources.yaml)에 기록되어 있다. 진단 보고서는 인용한 문서마다 W3C 원문 URL을 함께 표시한다.

## 핵심 코드 위치

> 현재 T01~T22 완료 기준이며 바뀔 수 있다. Task별 내역은 [TASKS.md](TASKS.md) 참조.

```text
mini-project/
├── src/a11y_investigator/
│   ├── cli.py                  CLI 진입점 `a11y-investigator` (analyze, policies init, policies check)
│   ├── config.py               모델 ID·경로·한도 설정
│   ├── report_markdown.py      보고서 Markdown 렌더링
│   ├── agent/                  그래프(graph.py), 노드(nodes.py), 수정 대상 결정(decision.py),
│   │                           프롬프트(prompts.py), 상태(state.py), Trace(trace.py)
│   ├── chains/                 Bedrock 모델(llm.py), 진단 체인(diagnosis.py), 수정 체인(improvement.py)
│   ├── tools/                  입력 파싱, 정적 분석 호출, 규칙–WCAG 매핑, 문서 조회,
│   │                           정책 로딩·검증, 수정 코드 재검증
│   ├── rag/                    W3C 문서 수집·청킹, 임베딩·Chroma, 인덱싱, 검색(retriever.py)
│   ├── templates/              새 프로젝트 지침 템플릿 (policies init)
│   ├── schemas/                정적 분석·근거·진단·보고서 스키마
│   └── middleware/safety.py    인용 검증·강등, 린트 우회 주석 차단
├── setup_env.py                설치 스크립트 (모든 OS·셸 공통)
├── a11y.py                     실행 런처 (가상환경 활성화 없이 CLI 실행)
├── analyzer-js/analyze.mjs     ESLint 9 + jsx-a11y 정적 분석기 (stdin → JSON)
├── knowledge/
│   ├── official/               WCAG·Understanding·Techniques·APG 원문 (W3C)
│   ├── project-policies/       프로젝트 정책 (예제: demo-ds)
│   └── manifests/              규칙–WCAG 매핑, 문서 출처·커밋 해시
├── evals/                      인-아웃 세트(datasets/), 실행기·지표·RAGAS, 리포트(reports/)
├── docs/                       사용 가이드, 평가 리포트, 결정 기록
├── examples/                   실행 예시 컴포넌트
├── tests/                      pytest (기본: LLM 호출 없음)
└── data/                       생성물, 커밋하지 않음 (chroma/ 인덱스, traces/ 실행 기록)
```
