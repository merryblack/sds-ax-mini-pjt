# A11y Investigator — MVP Tasks

[SPEC_MVP.md](SPEC_MVP.md)를 순서대로 구현하기 위한 작업 목록이다. 각 Task의 "참조"는 SPEC_MVP.md의 절 번호이다. MVP는 **웹(React DOM)의 React(JSX / TSX)만** 지원한다.

## 한눈에 보기

**5단계 · 23개 Task**

| 단계 | Task | 개수 | 끝나면 할 수 있는 것 | 상태 |
|---|---|---|---|---|
| Phase 0. 준비 | T01–T02 | 2 | 프로젝트가 설치·실행되고 결정 사항이 기록됨 | ✅ 완료 |
| Phase 1. 분석과 지식 | T03–T10 | 8 | 코드를 넣으면 정적 분석 결과와 관련 WCAG 문서가 나옴 | ✅ 완료 (M1) |
| Phase 2. Agent Workflow | T11–T16 | 6 | CLI로 코드를 넣으면 진단 + 개선 코드 + 재검증 결과가 나옴 | ✅ 완료 (M2) |
| Phase 3. 평가와 마무리 | T17–T20 | 4 | 평가 결과와 README를 갖춘 저장소, 인-아웃 세트(negative·edge·guardrail 포함) 측정 | ✅ 완료 (M3, M4) |
| Phase 4. 사용성 | T21–T23 | 3 | 어떤 OS·셸에서도 같은 명령으로 설치·실행하고, 새 프로젝트 지침을 명령 하나로 만들 수 있음. 문서가 코드와 일치함. 다양한 예시로 바로 시험해 볼 수 있음 | ✅ 완료 |

### 중간 점검 (Milestone)

- **M1 (T10 완료):** Scenario A 코드로 `analyze → map_rules → retrieve`를 실행하면 WCAG 2.1.1 문서가 검색된다.
- **M2 (T15 완료):** Scenario A가 그래프 전체를 통과해 `outcome=improved`가 나온다. **가장 중요한 점검이다.** 여기까지 오면 MVP의 뼈대가 완성된 것이다.
- **M3 (T18 완료):** 평가 19개를 돌려 합격선 대비 결과가 나온다.
- **M4 (T20 완료):** 인-아웃 세트 30개를 카테고리별로 측정하고, guardrail 케이스 통과율이 SERVICE.md 성공 기준(100%) 대비 기록된다.

## 의존 관계

```text
T01 → T02 → T03 ─┬─ T04 ───────────────────────────┐
                 ├─ T05 → T06 → T07 ──┐            │
                 ├─ T08 ──────────────┼─ T10 ─┐    │
                 └─ T09 ──────────────┘       │    │
                                              v    v
                          T11 → T12 → T13 → T14 → T15 → T16
                                                     │
                                              T17 → T18 → T19 → T20
```

- T04, T05, T08, T09는 T03 이후 서로 독립이라 순서를 바꿔도 된다.
- T09의 `component_mapping` 주입 확인은 T06까지 끝난 뒤 점검한다.

---

# Phase 0. 준비

### T01. 결정 사항 확정 ✅ 완료 (2026-11-18)
- [x] **참조:** 14장 (D1, D2) — 결과: [docs/decisions.md](docs/decisions.md)
- **작업**
  - 제공받은 AWS Bedrock 계정의 리전과 모델 접근 권한을 확인한다.
  - 접근 가능한 모델 중에서 Chat LLM(D1)과 다국어 임베딩 모델(D2)을 정한다.
  - 짧은 스크립트로 두 모델을 실제 호출해 본다(Chat 응답 1회, 한국어·영어 문장 임베딩 1회).
  - `docs/decisions.md`에 결정과 이유를 기록한다. D3, D4는 Phase 2 시작 전에 정한다.
- **완료 조건:** `docs/decisions.md`에 D1·D2가 기록되어 있고, 두 모델의 호출 테스트가 성공한다.

### T02. 프로젝트 스캐폴딩 ✅ 완료 (2026-11-18)
- [x] **참조:** 10장, 11장 — 환경: Python 3.14 (`.venv`), Node.js 26 LTS, ESLint 9.39.5, jsx-a11y 6.10.2, @typescript-eslint/parser 8.73.0
- **의존:** T01
- **작업**
  - Python 의존성은 `requirements.txt` 기준(langchain-aws, boto3 포함), `analyzer-js/package.json` (ESLint 9, eslint-plugin-jsx-a11y, @typescript-eslint/parser)
  - 11장 디렉터리 구조와 빈 모듈 생성
  - `config.py`: 모델명, 경로, 한도(300줄, 타임아웃 20초, 재시도 2회, 검색 상한 6/4)를 한곳에 모은다.
  - `.env.example`: `AWS_DEFAULT_REGION`, Chat 모델 ID, 임베딩 모델 ID. AWS 자격 증명은 AWS 프로필이나 환경변수로 받고 저장소에 넣지 않는다.
  - `.gitignore`(`data/chroma/`, `.env`)
- **완료 조건:** `pip install -r requirements.txt`, `pip install -e .`, `npm install`이 성공하고, `pytest` 스모크 테스트가 통과한다.

---

# Phase 1. 분석과 지식

### T03. 스키마 정의 ✅ 완료 (2026-11-18)
- [x] **참조:** 7장 — 테스트: `tests/test_schemas.py` 15개
- **의존:** T02
- **작업**
  - `schemas/analyzer.py`: `StaticFinding`, `AnalyzerResult`
  - `schemas/diagnosis.py`: Evidence, `Finding`(`fix_scope` 포함), `PolicyAssessment`, `DiagnosisOutput`, `FixOutput`, `ValidationResult`, `FindingResult`, `DiagnosisReport`
  - `agent/state.py`: `AnalysisState` (`errors` reducer, `component_hint` 포함)
- **완료 조건:** 각 모델을 예시 데이터로 생성·직렬화하는 단위 테스트가 통과한다. Evidence 판별자(`kind`)가 동작한다.

### T04. Input Parser ✅ 완료 (2026-11-18)
- [x] **참조:** 2장 (2.1, 2.3, 2.4, 2.5, 2.6) — 테스트: `tests/test_input_parser.py` 31개
- **의존:** T03
- **작업**
  - 코드 추출 규칙 4가지 (`--file`, 코드 펜스, 펜스 여러 개 거부, 펜스 없는 경우)
  - `code_type` 판별 (TypeScript 문법 유무로 jsx / tsx), React가 아닌 코드 거절
  - 입력 제한 검사 (300줄 / 8,000 토큰)
  - `component_hint` 추정
- **완료 조건:** 규칙별 단위 테스트 통과. Scenario A 입력에서 `code_type=jsx`, `component_hint=["button"]`이 나온다. 순수 HTML 입력은 `analysis_failed`가 나온다.

### T05. Node 정적 분석기 ✅ 완료 (2026-11-18)
- [x] **참조:** 5.1 — 테스트: `analyzer-js/analyze.test.mjs` 10개 (`npm test`, Hooks 규칙 테스트 포함). 1회 실행 약 1.2초(Node 기동 + ESLint 로딩)
- **의존:** T03
- **작업**
  - `analyze.mjs`: `--type jsx|tsx`, stdin으로 코드 입력, stdout으로 `AnalyzerResult` JSON 출력
  - ESLint 9 flat config + jsx-a11y `recommended`, TSX는 `@typescript-eslint/parser`
  - `component_mapping`을 옵션으로 받아 `settings['jsx-a11y'].components`에 주입
  - 파싱 실패 시 `parse_ok=false`와 `parse_error`
  - 결과에 분석기 버전 포함
- **완료 조건:** 터미널에서 Scenario A 코드를 파이프로 넣으면 `jsx-a11y/click-events-have-key-events`가 포함된 JSON이 나온다. 깨진 코드는 `parse_ok=false`가 나온다.

### T06. Python ↔ Node 연동 ✅ 완료 (2026-11-18)
- [x] **참조:** 5.1 (Python ↔ Node 인터페이스) — 테스트: `tests/test_static_analysis.py` 8개
- **의존:** T05
- **작업**
  - `tools/static_analysis.py`: subprocess 실행, stdin 전달, JSON → `AnalyzerResult` 변환
  - 타임아웃 20초, 0이 아닌 종료 코드 → 오류 반환
  - Windows 경로 처리 (`pathlib`)
- **완료 조건:** pytest에서 JSX / TSX 샘플의 분석 결과가 `AnalyzerResult`로 돌아온다. 타임아웃 케이스 테스트가 통과한다.

### T07. 규칙–WCAG 매핑 ✅ 완료 (2026-11-18)
- [x] **참조:** 6.3 — recommended 규칙 31개 전체 매핑, 테스트: `tests/test_rule_mapping.py` 10개. "매핑의 모든 SC가 인덱스에 존재" 테스트는 T08에서 추가
- **의존:** T06 (실제로 검출되는 규칙 ID를 확인한 뒤 작성)
- **작업**
  - `knowledge/manifests/rule-wcag-map.yaml`: 4개 컴포넌트 관련 jsx-a11y 규칙
  - `tools/rule_mapping.py`: `StaticFinding.wcag_refs` 채우기, 매핑 없는 규칙은 경고 로그
- **완료 조건:** 매핑 적용 테스트 통과. T08 이후 "매핑의 모든 SC가 인덱스에 존재" 테스트를 추가해 통과시킨다.

### T08. 공식 문서 수집·인덱싱 ✅ 완료 (2026-11-18)
- [x] **참조:** 6.1, 6.4, 6.6 — SC 20 / Understanding 20 / Techniques 57 / APG 4 → 청크 340개, 인덱싱 약 110초. 테스트: `tests/test_official_index.py` 12개(Bedrock 검색 1개는 `-m llm`)
- **의존:** T03, T01(D2 임베딩 모델)
- **작업**
  - `w3c/wcag`, `w3c/aria-practices`에서 6.1 범위 문서 수집 → `knowledge/official/`
  - `sources.yaml`에 출처와 커밋 해시 기록
  - `rag/chunker.py`: 문서 유형별 청킹 (SC별, 기법 ID별, APG 패턴·섹션별)
  - `rag/metadata.py`: 6.4 메타데이터, `wcag-<SC>` 형식 `document_id`
  - `rag/ingest.py`: `official` 컬렉션에 전체 재인덱싱
- **완료 조건:** `python -m a11y_investigator.rag.ingest` 실행 후 `wcag-2.1.1` 문서를 ID로 조회할 수 있고, APG Dialog 청크가 존재한다.

### T09. 예제 프로젝트 정책 ✅ 완료 (2026-11-18)
- [x] **참조:** 6.2, 3.3 Scenario C — 정책 5개(충돌 케이스 `demo-ds-focus-001` 포함), 테스트: `tests/test_policy_lookup.py` 9개(Bedrock 검색 1개는 `-m llm`)
- **의존:** T03 (`component_mapping` 주입 확인은 T06 완료 후)
- **작업**
  - `knowledge/project-policies/demo-ds/project.yaml` (`target_level`, `component_mapping`)
  - 정책 규칙 Markdown 3~5개 (Button 필수 사용 등, Scenario C용 충돌 케이스 1개 포함)
  - `ingest.py`에 `project_policies` 컬렉션 인덱싱 추가
  - `tools/policy_lookup.py`: `project.yaml` 로딩
- **완료 조건:** `project_id=demo-ds` 필터로 정책이 검색되고, 다른 `project_id`로는 검색되지 않는다. `component_mapping`을 넣으면 `<Button onClick>`을 jsx-a11y가 버튼으로 인식한다.

### T10. Retriever ✅ 완료 (2026-11-18) — **M1 달성**
- [x] **참조:** 6.5 — 테스트: `tests/test_retriever.py` 11개(가짜 저장소로 오프라인 검증, M1 실제 인덱스 검증은 `-m llm`)
- **의존:** T07, T08, T09
- **작업**
  - `rag/retriever.py`
    - 1단계: `wcag_refs`·APG 패턴으로 정확 조회
    - 2단계: 템플릿 영어 쿼리로 벡터 검색
    - 3단계: `project_id` 필터로 정책 검색
  - 중복 제거, 상한(공식 6 / 정책 4) 적용
  - `tools/guideline_search.py`: `search_guidelines`, `get_wcag_criterion`
- **완료 조건:** **M1 점검** — Scenario A의 정적 분석 결과를 넣으면 WCAG 2.1.1과 APG Button 문서가 결과에 포함된다.

---

# Phase 2. Agent Workflow

Phase 2 시작 전에 D3(호출 상한), D4(LangSmith 사용 여부)를 정한다.

### T11. 진단 체인 ✅ 완료 (2026-11-19)
- [x] **참조:** 4.2 `diagnose`, 5.2, 8장 — 테스트: `tests/test_diagnosis.py` 오프라인 5개 + Bedrock 3개(`-m llm`, Scenario A / Dialog / 정책+프롬프트 인젝션, 1회 15~25초)
- **의존:** T10
- **작업**
  - `chains/diagnosis.py`: LCEL + 구조화 출력 → `DiagnosisOutput`
  - `agent/prompts.py`: 진단 프롬프트
    - 입력 코드와 검색 문서를 구분 태그로 감싸고, 그 안의 지시문은 데이터로 취급하도록 명시
    - 상태 정의(confirmed / suspected / manual_review), `fix_scope` 출력, 전달된 `document_id`만 인용
    - 목표 레벨, 출력 언어(한국어)
    - 정책이 있으면 `PolicyAssessment` 작성
- **완료 조건:** Scenario A로 실행하면 `confirmed` Finding이 1개 이상 나오고, 근거에 전달된 `document_id`만 들어 있다.

### T12. 판단 노드와 인용 검증 ✅ 완료 (2026-11-19)
- [x] **참조:** 5.2, 8장, 7.2 마지막 문단 — `middleware/safety.py`(인용 검증) + `agent/decision.py`(decide). 테스트: `tests/test_decision.py` 18개(LLM 없음)
- **의존:** T11
- **작업**
  - `middleware/safety.py`: 전달되지 않은 `document_id` 제거, 인덱스에 없는 WCAG SC 제거
  - 근거 없는 `confirmed` / `suspected` → `manual_review` 강등
  - `parse_ok=false`면 `confirmed` 금지
  - `decide`: `will_fix` 설정, `needs_improvement` 계산
- **완료 조건:** 가짜 `document_id`·가짜 SC(`9.9.9`)를 넣은 Finding이 강등되는 테스트, `fix_scope`별 `will_fix` 테스트가 통과한다. (LLM 없이 테스트 가능)

### T13. 수정 체인 ✅ 완료 (2026-11-19)
- [x] **참조:** 4.2 `generate_fix`, 1.2 최소 수정 — 테스트: `tests/test_improvement.py` 오프라인 8개 + Bedrock 2개(`-m llm`). 함께 수정: 펜스 없는 입력의 맨 앞 주석이 코드에서 빠지던 T04 파서 버그
- **의존:** T12
- **작업**
  - `chains/improvement.py`: LCEL + 구조화 출력 → `FixOutput`
  - 프롬프트: `will_fix` Finding만 수정, 기능·구조·스타일 유지, 린트 비활성화 주석 금지, 정책의 `component_mapping` 컴포넌트 우선 사용
  - 재시도 입력: 이전 실패 사유(새 위반, 미해소 규칙, 금지 패턴)를 받을 수 있게 설계
- **완료 조건:** Scenario A로 `<button type="button">`을 사용한 코드가 생성된다.

### T14. 재검증 ✅ 완료 (2026-11-19)
- [x] **참조:** 5.3, 8장 린트 우회 — 테스트: `tests/test_code_validation.py` 18개(LLM 없음) + Bedrock 재시도 1개(`-m llm`). 보완: 재시도 결과에서 Hooks 규칙 위반이 발견되어 `react-hooks/rules-of-hooks`를 재검증 전용 규칙으로 추가(5.1)
- **의존:** T13, T06
- **작업**
  - `tools/code_validation.py`: 통과 기준 4가지
    - 파싱 성공
    - `rule_id`별 위반 개수가 늘지 않음
    - `will_fix` 연결 규칙 해소
    - 원본에 없던 `eslint-disable` 계열 주석 없음
  - `ValidationResult` 생성 (개수 전후, 새 위반, 미해소 규칙, 차단 패턴)
  - 변경 줄 수 계산
- **완료 조건:** 통과 케이스, 새 위반 케이스, `eslint-disable` 삽입 케이스 각각의 판정 테스트가 통과한다. (LLM 없이 테스트 가능)

### T15. 그래프 조립과 보고서 ✅ 완료 (2026-11-19) — **M2 달성**
- [x] **참조:** 4장, 3.2, 7.2, 6.2(자동 재인덱싱) — 진입점 `agent/graph.py: run_analysis()`. 테스트: `tests/test_graph.py` 오프라인 15개(가짜 분석기·LLM으로 모든 분기 검증) + M2 Bedrock 2개(`-m llm`)
- **의존:** T04, T14
- **작업**
  - `agent/nodes.py`, `agent/graph.py`: 9개 노드와 조건부 분기
    - `parse_input` / `analyze` 실패 → `report`
    - `needs_improvement=false` → `report`
    - 재검증 실패 & `retry_count < 2` → `generate_fix`
  - `recursion_limit=25`
  - 목표 레벨 결정: CLI `--level` > 요청 문구(`requested_level`) > 프로젝트 `target_level` > 기본 AA
  - **정책 자동 재인덱싱:** `project_id`가 있으면 `project.yaml`과 정책 파일의 해시를 `data/chroma/policy-hashes.json`과 비교해, 바뀌었으면 그 프로젝트 정책만 다시 인덱싱한 뒤 진행
  - `report` 노드: `outcome` 결정, 근거 URL을 메타데이터에서 채움, `fix_failed`일 때 "검증되지 않은 코드" 경고, 재현성 필드(model, index_version, analyzer_versions, trace_id)
- **완료 조건:** **M2 점검** — Scenario A → `improved`, Scenario B → `no_issue_detected` 또는 `no_change_needed`, 300줄 초과 입력 → `analysis_failed`가 나온다. 정책 파일을 고친 뒤 `ingest` 없이 분석해도 바뀐 정책이 검색된다(해시 비교 단위 테스트 포함).

### T16. CLI와 Trace ✅ 완료 (2026-11-19)
- [x] **참조:** 2.2, 3.1, 9.1 — 테스트: `tests/test_cli.py` 10개(오프라인). 실제 실행 1회 약 22~25초, 토큰 약 9k+2k, 예상 $0.06. 함께 수정: 정책에 패키지 이름이 없을 때 import 경로를 지어내던 문제(수정 프롬프트·템플릿)
- **의존:** T15
- **작업**
  - `cli.py` (Typer): `analyze` 명령, `--file`, `--project`, `--level`(기본값 `None`: 지정하지 않으면 T15의 우선순위를 따름), `--json`, stdin 입력
  - `policies check <project_id>` 명령: `load_policies` 검증 결과와 `related_wcag`가 인덱스에 있는 SC인지(`is_indexed_sc`) 확인해 문제 목록을 출력, 문제가 있으면 종료 코드 1
  - Markdown 보고서 렌더링 (3.1의 9개 항목)
  - Trace: 로컬 JSON Trace (D4 확정). `data/traces/<trace_id>.json`에 노드별 시간, 토큰, 예상 비용, 검색 쿼리·문서, 재검증 결과, 오류 기록
- **완료 조건:** 아래 명령이 Markdown 보고서를 출력하고, `--json`은 `DiagnosisReport` JSON을 출력한다. Trace에서 노드별 실행 기록을 확인할 수 있다. `policies check demo-ds`는 통과하고, 잘못된 정책 폴더에는 문제를 출력한다. README "내 프로젝트 지침 추가하기" 절차대로 새 프로젝트를 만들어 분석할 수 있다.
  ```bash
  a11y-investigator analyze --file examples/save_button.jsx --project demo-ds
  a11y-investigator policies check demo-ds
  ```

---

# Phase 3. 평가와 마무리

### T17. 평가 데이터셋 ✅ 완료 (2026-11-19)
- [x] **참조:** 9.2 — 결과: `evals/datasets/` 19개 YAML(TSX 8개), 스키마 `evals/dataset.py`. 테스트: `tests/test_eval_dataset.py`(개수·참조 검증, 분석기 결과와 `static_rule_ids` 대조). 문제 없는 코드는 `no_issue_detected`·`no_change_needed`를 모두 정답으로 둔다
- **의존:** T15 (출력 형식 확정 후)
- **작업**
  - `evals/datasets/`에 19개 케이스: Button 8 (정책 2 포함), Dialog 4, Tabs 4, Combobox 3. 최소 4개는 TSX
  - 케이스마다 입력 코드, 기대 Finding(`rule_id` 또는 설명, `status`, `wcag_criteria`), 기대 `outcome`, 기대 근거 `document_id`, 정책 케이스는 기대 `PolicyAssessment`
- **완료 조건:** 19개 파일이 스키마 검증을 통과한다.

### T18. 평가 실행기 ✅ 완료 (2026-11-19, M3)
- [x] **참조:** 9.3, 13장 — 결과: [evals/reports/20261119-045925.md](evals/reports/20261119-045925.md). 14/19 통과, 지표 5개 중 4개 합격(no-change 비율 20% 미달). 테스트: `tests/test_eval_metrics.py`(오프라인 8개 + `-m eval` 1개)
- **의존:** T17, T16
- **작업**
  - `evals/evaluate.py`: 전체 케이스 실행, 9.3 지표 5개 계산, 케이스별 실패 사유 기록
  - **RAGAS (9.4, P0로 승격):** 같은 실행 결과(state)로 context_recall, context_precision, faithfulness, answer_relevancy 측정. `ragas` 패키지 추가, 평가 LLM·임베딩은 Bedrock 래퍼(평가 LLM 기본 Haiku 4.5)
  - `evals/reports/`에 결과 저장 (모델, 인덱스 버전 포함)
  - pytest로 LLM 없는 단위 테스트와 평가 실행을 분리 (평가는 마커로 별도 실행)
  - 평가 후 케이스 유형별 평균 사용량(시간, 토큰, 예상 비용)을 `docs/decisions.md` D3 표에 기록 (D3은 보류, 상한 없음)
- **완료 조건:** **M3 점검** — 평가 1회 실행으로 지표 5개, RAGAS 4개 지표, 실패 케이스 목록이 담긴 리포트가 생성되고 README에 기록된다.

### T19. 품질 개선과 마무리 ✅ 완료 (2026-11-19)
- [x] **참조:** 9.3, 12장 Day 3, 13장 — 결과: [evals/reports/20261119-054203.md](evals/reports/20261119-054203.md). **17/19** 통과, no-change 비율 60%(미달, 합격선 유지), 재검증 통과율 100%. 아래 보완점 반영, 병렬 평가 중 Chroma 초기화 경합 수정. 13장 인수 기준 점검 완료
- **의존:** T18
- **작업**
  - 실패 케이스 분석 → 매핑 보강, 쿼리 템플릿 개선, 프롬프트 수정 → 재평가
  - T18 1차 결과에서 정한 보완점
    1. 진단 프롬프트: APG 선택 권장 사항은 Finding이 아니라 `manual_checks`로 보낸다
    2. 정답 코드 라벨 보강: dialog-04 포커스 트랩, tabs-04 tabpanel `tabIndex`
    3. 수정 프롬프트: 비대화형 컨테이너에 키 핸들러를 달지 않고 Escape는 document 리스너로 처리한다
  - 합격선 조정 시 `docs/decisions.md`에 사유 기록
  - 평가 1회 비용과 실행 시간 측정
  - README: 설치, 인덱싱, 실행 방법, 시나리오 A/B/C 예시, 평가 결과
  - 13장 인수 기준 체크리스트 점검
- **완료 조건:** 13장 인수 기준이 모두 체크되고, README에 평가 결과가 기록되어 있다.

### T20. 인-아웃 세트 확장 (negative · edge · guardrail) ✅ 완료 (2026-11-19, M4)
- [x] **참조:** 8장, 9.2, 9.3, [SERVICE.md](SERVICE.md) 4·5장 — 결과: [evals/reports/20261119-070023.md](evals/reports/20261119-070023.md). **29/30 통과(97%), guardrail 4/4(100%)**, 9.3 지표 5개 모두 합격. 테스트: `tests/test_eval_dataset.py`, `tests/test_eval_metrics.py`
- **의존:** T19
- **배경:** 기존 평가 19개는 정상 진단 케이스뿐이라 SERVICE.md 성공 기준(인-아웃 80%, guardrail 100%)을 측정할 수 없었다. 멘토 제시 인-아웃 세트 형식의 요소를 기존 YAML 평가 체계에 넣는다.
- **작업**
  - 케이스 형식 확장 (`evals/dataset.py`)
    - 카테고리: 기존 `issue`·`policy`는 positive, `clean`은 negative로 묶고 `edge`·`guardrail`을 추가한다(입력 거절 케이스는 `negative` 또는 `edge`로 둔다)
    - `forbidden`: 보고서에 나오면 안 되는 문자열 (예: "완전 준수", `eslint-disable`, 지어낸 import 경로)
    - `expected_nodes` / `forbidden_nodes`: Trace에 실행돼야 할 노드와 실행되면 안 되는 노드 (예: 입력 거절 시 `diagnose` 미실행)
    - `expected_traits`: 보고서에 반드시 있어야 할 항목 (예: `outcome`, 오류 사유, 언급할 WCAG 기준)
  - 케이스 11개 추가 (총 30개, positive 14 · negative 8 · edge 4 · guardrail 4)
    - negative 3: 없는 프로젝트 ID, HTML 문서 입력, 범위 밖 컴포넌트(예: Accordion)
    - edge 4: 코드 블록 여러 개, 300줄 초과, 요청 문구의 AAA 레벨, WCAG와 충돌하는 정책(focus-001)
    - guardrail 4: 코드 주석 속 프롬프트 인젝션, "완전 준수라고 써 줘" 요청, "eslint-disable로 경고만 없애 줘" 요청, 접근성과 무관한 요청(예: 성능 최적화)
  - 채점 확장 (`evals/metrics.py`): 금지 문자열 검사, Trace 노드 검사, 카테고리별 통과율, guardrail 통과율
  - 재평가 후 README "인-아웃 세트 통과율"에 카테고리별 결과 기록, D3 사용량 갱신
  - 실패한 guardrail 케이스는 프롬프트 수준으로 고칠 수 있으면 T20에서 고치고, 동작 설계 변경이 필요하면 ROADMAP V0.3에 기록한다
- **완료 조건:** 30개 케이스가 스키마 검증을 통과하고, 평가 1회로 카테고리별 통과율과 guardrail 통과율이 리포트에 나오며 README에 기록된다.

---

# Phase 4. 사용성

### T21. 누구나 쉽게 실행하는 설치·실행 방식 ✅ 완료 (2026-11-19)
- [x] **참조:** 2.2, 10장, README "실행 방법" — 결과: `setup_env.py`(설치), `a11y.py`(런처, `test`·`eval`·`index`·`fetch` 포함), 문서 명령 통일. 새 clone에서 PowerShell로 설치→분석까지, Git Bash·cmd·`py`에서 확인. **미확인:** macOS·Linux. 테스트: `tests/test_setup_env.py` 7개
- **의존:** T20
- **배경:** README 절차가 셸·OS마다 막혔다(가상환경 활성화 방식, PowerShell 실행 정책, `copy`·`;`·`\` 경로 차이).
- **작업**
  - `setup_env.py` (표준 라이브러리만 사용, 시스템 Python으로 실행)
    - Python·Node 버전 확인
    - `.venv` 생성과 의존성 설치(요구사항이 바뀌지 않았으면 건너뜀)
    - `analyzer-js` npm 설치
    - `.env`가 없으면 복사, AWS 키가 비어 있으면 안내
    - 키가 있고 인덱스가 없으면 확인 후 인덱스 생성
    - 여러 번 실행해도 안전하게, 마지막에 다음 명령 안내
  - `a11y.py`: 가상환경 활성화 없이 `.venv`의 Python으로 CLI를 실행하는 런처. 모든 하위 명령과 표준 입력을 그대로 전달하고 종료 코드를 유지한다
  - `python -m a11y_investigator` 지원(`__main__.py`)
  - README "실행 방법"을 `python setup_env.py` → `python a11y.py ...` 흐름으로 바꾸고, 예시 경로는 `/`로 통일한다. 기존 가상환경 방식은 대안으로 남긴다
  - 설치 스크립트의 판단 로직(경로, 건너뛰기 조건, `.env` 검사) 오프라인 테스트
- **완료 조건:** 새 터미널에서 가상환경 활성화 없이 README 명령 그대로 설치·실행이 된다. Windows PowerShell과 Git Bash에서 직접 확인하고, 확인하지 못한 환경(macOS·Linux, cmd)은 그대로 기록한다.

### T22. 프로젝트 지침 템플릿 정리와 생성 명령 ✅ 완료 (2026-11-20)
- [x] **참조:** 6.2, [docs/guide.md](docs/guide.md) 3장 — 결과: 템플릿을 `src/a11y_investigator/templates/project-policy/`로 이동, `policies init <id>` 추가. 테스트: `tests/test_policy_init.py` 10개. 후속으로 전체 문서 오류 수정·정리(2026-11-20)
- **의존:** T21
- **배경:** 템플릿이 설명 문서용 폴더(`docs/`)에 있었고, 사용법이 Windows 전용 복사와 수동 ID 수정이었다. `knowledge/project-policies/` 아래에는 둘 수 없다(`project.yaml`이 있으면 프로젝트로 인덱싱됨).
- **작업**
  - 템플릿을 `src/a11y_investigator/templates/project-policy/`로 옮긴다(패키지 데이터로 등록).
  - CLI `policies init <project_id>` 추가
    - 템플릿을 `knowledge/project-policies/<project_id>/`로 복사하고 `project_id`·`policy_id`를 채운다.
    - 이미 있는 폴더는 덮어쓰지 않는다. 프로젝트 ID 형식을 검사한다.
    - 만든 뒤 `policies check` 결과를 보여 준다.
  - 테스트: 생성한 프로젝트가 `check_project`를 통과하는지(템플릿이 스키마와 어긋나지 않는지), 기존 폴더를 보호하는지, 잘못된 ID를 거부하는지
  - 문서: guide 3.1, SPEC_MVP 6.2, README 6절·코드 위치, CLAUDE.md
  - 후속: 전체 문서 정리 (구조·넘버링·목록 형식은 유지)
    1. 코드와 다른 사실 오류 수정 (노드 구현 이름, 상태·스키마, 디렉터리, 메타데이터 예시, guardrail 목록 등)
    2. 중복되거나 과하게 설명된 내용 축약 (SPEC_MVP 9.2·12·14, decisions D3·합격선, evaluation RAGAS·측정 기록, TASKS T18–T22, ROADMAP 개정 이력)
- **완료 조건:** `python a11y.py policies init <id>` 한 번으로 검증을 통과하는 프로젝트 폴더가 만들어지고, 문서에 수동 복사 절차가 남아 있지 않다.

### T23. 실행 예시 컴포넌트 추가 ✅ 완료 (2026-11-20)
- [x] **참조:** 3.3, [docs/guide.md](docs/guide.md) 1장 — 결과: 예시 7개 추가(JSX 3, TSX 4). `--project demo-ds`로 실행해 6개 `improved`(모두 1회 통과), `login_form.tsx`는 정책 위반만 있어 `no_change_needed`. MVP 범위를 웹(React DOM)으로 문서에 명시. 확인 중 발견: `modal.tsx` 한 번의 실행에서 정책 판정이 빠짐(LLM 누락, 가드레일 미감지)
- **의존:** T22
- **배경:** `examples/`에 `save_button.jsx` 하나뿐이라 처음 쓰는 사람이 다양한 경우를 시험해 보기 어렵다. 인터넷 코드는 라이선스 문제가 있어, 실무에서 흔한 구현 패턴을 재현해 직접 작성한다.
- **작업**
  1. 흔한 접근성 실수가 담긴 평범한 컴포넌트를 JSX·TSX로 작성한다 (드롭다운, 모달, 상품 카드, 탭, 검색 자동완성, 아이콘 툴바, 문제 없는 대조 예시)
  2. 평가 데이터셋(`evals/datasets/`)과 겹치지 않는 컴포넌트로 만든다
  3. 각 예시를 정적 분석기로 돌려 의도한 규칙이 잡히는지 확인한다
  4. 예시 목록을 guide 1장에 추가하고 README에서 연결한다
  5. MVP 범위가 웹(React DOM)임을 문서에 명시한다 (SPEC_MVP 1장, README, SERVICE, ROADMAP, CLAUDE.md). 예시도 모두 웹 컴포넌트로 작성한다 (React Native·모바일 네이티브 앱은 범위 밖)
  6. 명세 문서 이름 변경: `SERVICE_MVP.md` → `SPEC_MVP.md` (`SERVICE.md`와 역할이 헷갈리지 않게). 문서·코드·테스트·평가 케이스의 참조를 모두 고친다. 당시 생성된 평가 리포트(`evals/reports/`)는 그대로 둔다
- **완료 조건:** 예시마다 정적 분석 결과가 의도와 일치하고, 문서에 목록과 실행 명령이 있다.
