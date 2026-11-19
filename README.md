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
pytest                                # 기본: LLM 호출 없음
pytest -m llm                         # Bedrock 호출 테스트 (비용 발생)
cd analyzer-js; npm test; cd ..       # 정적 분석기 테스트
```

`-m llm` 테스트는 현재 9개, 약 2분 걸린다. 현재 계정에는 Bedrock 일일 토큰 한도가 있어 반복 실행하면 `ThrottlingException`이 날 수 있다(한도와 대응 방법은 바뀔 수 있음, [docs/decisions.md](docs/decisions.md) 참조).

### 5. 분석 실행

> CLI는 T16에서 구현 예정이다.

```powershell
a11y-investigator analyze --file Component.tsx --project demo-ds
```

지금은 Python에서 바로 실행할 수 있다.

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

**3) 검증** (T16에서 구현 예정)

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
- context_recall: 0.XX
- context_precision: 0.XX
- faithfulness: 0.XX
- answer_relevancy: 0.XX

## 인-아웃 세트 통과율 (자체 평가)
- 1차 (Day 9 종료): XX / XX 통과
- 2차 (Day 10 개선 후): XX / XX 통과
- 개선폭: +XX 건 (주요 개선 사항: ...)

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

## 출처와 라이선스

`knowledge/official/`의 WCAG 2.2, Understanding WCAG, Techniques for WCAG, WAI-ARIA Authoring Practices Guide 문서는 W3C의 저작물이며 [W3C Software and Document License](https://www.w3.org/copyright/software-license/)에 따라 포함했다. 수집한 원본 URL과 GitHub 커밋 해시(`w3c/wcag`, `w3c/aria-practices`)는 [knowledge/manifests/sources.yaml](knowledge/manifests/sources.yaml)에 기록되어 있다. 진단 보고서는 인용한 문서마다 W3C 원문 URL을 함께 표시한다.

## 핵심 코드 위치

> 현재 Phase 2 진행 중(M2 달성)이며, 진행에 따라 바뀐다. ✅ 구현됨 · ⏳ 예정(괄호 안은 담당 Task, 최신 상태는 [TASKS.md](TASKS.md) 참조)

```text
mini-project/
├── src/a11y_investigator/
│   ├── cli.py                  ⏳ CLI 진입점 `a11y-investigator` (T16)
│   ├── config.py               ✅ 모델 ID·경로·한도 설정
│   ├── agent/
│   │   ├── state.py            ✅ LangGraph 상태
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
├── evals/                      ⏳ 평가 데이터셋·실행기 (T17, T18)
├── tests/                      ✅ pytest (LLM 호출 없는 기본 테스트 + `-m llm`)
└── data/chroma/                검색 인덱스 (생성물, 커밋하지 않음)
```