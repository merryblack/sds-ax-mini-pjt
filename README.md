# 미니 PJT: A11y Investigator

## 무엇을 푸나
React 컴포넌트의 접근성 위반을 찾아도 WCAG 근거와 올바른 수정 방법을 확인하는 데 시간이 오래 걸리고 결과가 사람마다 다르다. A11y Investigator는 정적 분석과 WCAG·APG 근거 검색으로 문제를 진단하고, 재검증된 개선 코드를 돌려준다.

문서: [SERVICE.md](SERVICE.md) (서비스 정의) · [SERVICE_MVP.md](SERVICE_MVP.md) (MVP 구현 명세) · [TASKS.md](TASKS.md) (작업 목록) · [ROADMAP.md](ROADMAP.md) (장기 계획)

## 활용한 패턴 (Day 1~7)
- Day X: 패턴 — 어떻게 활용
- Day Y: 패턴 — ...

## 아키텍처
(간단 다이어그램 or 텍스트 설명)

## 실행 방법

### 준비물
- Python 3.11 이상 (개발 환경: 3.14)
- Node.js 20 이상 (개발 환경: 26 LTS) — 정적 분석기(ESLint + jsx-a11y) 실행용
- AWS Bedrock 접근 권한 — Chat: `us.anthropic.claude-sonnet-4-6`, 임베딩: `amazon.titan-embed-text-v2:0` ([docs/decisions.md](docs/decisions.md))

### 1. 설치

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
cd analyzer-js; npm install; cd ..
```

### 2. 환경변수

`.env.example`을 `.env`로 복사하고 AWS 자격 증명을 채운다. `.env`는 커밋하지 않는다.

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

### 5. 분석 실행

> CLI는 T16에서 구현 예정이다.

```powershell
a11y-investigator analyze --file Component.tsx --project demo-ds
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
- 시도했지만 실패한 접근 · 왜 실패했는가
- 최종 채택한 접근 · 왜 그것으로 갔는가
- 남은 한계 · 향후 개선 방향

## 핵심 코드 위치

> 진행 중(Phase 1 완료). ✅ 구현됨 · ⏳ 예정(괄호 안은 담당 Task, [TASKS.md](TASKS.md) 참조)

```text
mini-project/
├── src/a11y_investigator/
│   ├── cli.py                  ⏳ CLI 진입점 `a11y-investigator` (T16)
│   ├── config.py               ✅ 모델 ID·경로·한도 설정
│   ├── agent/
│   │   ├── state.py            ✅ LangGraph 상태
│   │   ├── decision.py         ✅ decide: 인용 검증 적용 + 수정 대상 결정 (일반 코드)
│   │   ├── graph.py            ✅ 메인 에이전트 그래프, 보고서 조립, run_analysis() 진입점
│   │   ├── nodes.py            ✅ 9개 노드와 분기 조건
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