# A11y Investigator
## Evidence-based Accessibility Analysis & Improvement Agent
**Project Overview & Long-term Roadmap**

| 항목 | 내용 |
|---|---|
| 문서 버전 | v0.5 |
| 상태 | MVP 개발 전 (MVP 이후 장기 계획 수립에 사용) |
| 프로젝트 유형 | Agentic RAG · Developer Tool |
| 개발 형태 | 개인 프로젝트 |
| 입력 언어 | React(JSX/TSX) — HTML + JavaScript는 V0.3부터 |
| Agent Framework | LangChain, LangGraph |
| RAG 저장소 | Chroma |
| 주요 언어 | Python + JavaScript/TypeScript |
| 장기 목표 | 접근성 진단·수정·검증 자동화 플랫폼 |

---

# 0. 문서 구성

| 문서 | 역할 | 언제 보는가 |
|---|---|---|
| **ROADMAP.md** (이 문서) | 프로젝트가 왜 필요하고 어디로 가는가. 배경, 목적, 설계 원칙, 제품 범위, 우선순위, 버전별 장기 계획 | MVP 이후 다음 단계를 계획하거나, 판단 기준이 필요할 때 |
| [SERVICE_MVP.md](SERVICE_MVP.md) | 2~3일 MVP(P0)를 어떻게 구현하는가. 입출력, 그래프, 판단 규칙, 스키마, 일정, 인수 기준 | MVP를 구현할 때 |

두 문서가 충돌하면 설계 원칙은 이 문서, MVP 구현 상세는 SERVICE_MVP.md를 따른다.

---

# 1. 프로젝트 개요

## 1.1. 배경

기존 범용 코딩 Agent는 접근성을 고려한 코드 생성과 수정이 가능하다. 그러나 접근성 기준을 일관되게 검증하고, 프로젝트 고유의 개발 정책을 적용하며, 그 판단의 근거를 추적하려면 별도의 검증 체계가 필요하다.

또한 ESLint와 같은 정적 분석 도구는 규칙 기반 오류 탐지에 효과적이지만, 개발 의도와 복잡한 상호작용 및 프로젝트별 정책을 모두 해석하기 어렵다.

A11y Investigator는 정적 분석 도구, LLM 기반 추론, RAG 지식베이스를 결합하여 코드의 접근성 문제를 진단하고 개선된 코드를 제공하는 전문 Agent이다.

## 1.2. 목적

### Primary Goal — 실용적인 Agent 개발 기술 습득

실제 문제를 해결하는 Agent를 직접 설계하고 구현하는 기술을 습득한다.

| 학습 대상 | 단계 |
|---|---|
| LangChain / LCEL 및 구조화 출력 | MVP |
| LangGraph 기반 실행 흐름과 상태 관리 | MVP |
| RAG 구축 및 검색 품질 개선 | MVP |
| Guardrails | MVP |
| Observability 및 Trace | MVP |
| 평가 데이터셋 기반 품질 측정 | MVP |
| ReAct, MCP, RAGAS, LLM-as-Judge, Middleware | P1 (V0.3) |
| HITL, Multi-Agent, Long-term Memory | P2 (V0.4 이후) |

### Secondary Goal — 실용적인 접근성 개발 도구 구축

실무에서 사용할 수 있는 접근성 진단 및 개선 도구를 만든다.

범용 코딩 Agent보다 뛰어난 코드 생성기를 만드는 것이 아니라, 접근성 표준과 프로젝트 맥락을 활용하여 더 일관되고 검증 가능한 개선 결과를 제공하는 것을 목표로 한다.

## 1.3. 제품 비전

**프로젝트의 개발 규칙과 공식 접근성 표준을 이해하고, 코드를 진단하여 문제를 설명하고 개선된 코드를 생성하는 Accessibility Coding Agent.**

MVP 이후 로컬 프로젝트 파일 수정, 동적 분석, 범용 코딩 Agent 연동으로 확장한다(5장).

**최우선 학습 목표는 실제로 동작하는 Agent를 구축하는 것이고, 제품 목표는 검증 가능하고 실무에 활용할 수 있는 접근성 코드 개선 도구를 만드는 것이다.**

---

# 2. 핵심 설계 원칙

MVP와 이후 모든 버전의 구현과 판단은 이 원칙을 따른다.

## 2.1. Evidence-first

접근성 문제에 대한 진단에는 확인 가능한 근거가 포함되어야 한다.

근거 자료는 다음과 같다.

- WCAG 2.2
- WAI-ARIA 및 APG
- 실제 정적 분석 결과
- 프로젝트별 개발 지침
- 검증된 과거 사례 (MVP 이후)

근거가 불충분하거나 정적 분석으로 확정할 수 없는 문제는 수동 검증 대상으로 분류한다.

## 2.2. Deterministic-first

기계적으로 검증할 수 있는 부분은 일반 프로그램을 우선 사용한다.

LLM은 문맥 해석, 추가 조사, 개선 방법 판단 및 코드 생성에 집중한다.

필수 검사는 Agent의 자율적 선택에 맡기지 않고 반드시 수행한다.

## 2.3. Project-aware

프로젝트별 코딩 컨벤션과 접근성 관련 정책을 반영한다.

단, 프로젝트 정책과 공식 접근성 기준은 별도로 평가한다.

프로젝트 정책을 준수하더라도 접근성 요구사항을 위반할 수 있으므로, 정책 준수가 접근성 준수를 의미하지는 않는다. 둘이 충돌하면 공식 접근성 기준을 우선한다.

## 2.4. Minimal Modification

개선 코드를 생성할 때는 기존 기능과 구조를 최대한 유지한다.

- 불필요한 리팩터링 지양
- 비즈니스 로직 유지
- 기존 이벤트 동작 유지
- 기존 스타일 및 DOM 구조 최대한 보존
- 접근성 개선에 필요한 변경에 집중

## 2.5. Validation-first

생성된 개선 코드는 가능한 범위에서 정적 분석을 다시 수행한다.

문법 오류, 명확한 접근성 오류 및 기존 코드 대비 새로운 문제 발생 여부를 검사한다.

정적 분석 통과만으로 완전한 접근성 적합성을 보증하지 않으며, "접근성 완전 준수"처럼 검증 범위를 넘어서는 표현은 사용하지 않는다.

## 2.6. Reproducibility

진단 및 개선 과정에 사용된 문서, 도구, 모델, 실행 결과를 기록하여 재현 가능한 검증 체계를 구축한다.

## 2.7. Human-in-the-Loop for Writes

사용자의 파일이나 저장소를 실제로 변경하는 기능(V0.5 이후)은 반드시 사용자 승인을 거친다. MVP는 개선 코드를 출력만 하므로 승인 절차가 없다.

---

# 3. 제품 범위

## 3.1. 제품이 하는 일

```text
코드 입력 → 정적 분석 → 근거 검색 → 진단 → 개선 여부 판단 → 개선 코드 생성 → 재검증 → 보고서
```

- **입력:** React(JSX/TSX) 코드(V0.3부터 HTML + JavaScript 포함), 선택적으로 프로젝트 식별자. MVP는 사용자가 직접 입력한 코드만, V0.4 이후는 로컬 프로젝트 파일까지.
- **출력:** 진단 결과와 근거, 프로젝트 정책 적합성, 필요한 경우 개선된 전체 코드, 재검증 결과, 수동 검증 항목. V0.5 이후는 Diff와 실제 파일 변경까지.

## 3.2. 지식 계층

| 계층 | 내용 | 단계 |
|---|---|---|
| Layer 1 — Official Standards | WCAG 2.2, Understanding, Techniques, WAI-ARIA APG | MVP |
| Layer 2 — Project Policies | 프로젝트 접근성 지침, 디자인 시스템 문서, 커스텀 컴포넌트 규칙, 개발 컨벤션 | MVP |
| Layer 3 — Verified Cases | 과거 접근성 인증 이슈, 해결된 버그, VoiceOver / TalkBack 검증 사례, 수정 및 회귀 이력 | MVP 이후 |

프로젝트 정책은 프로젝트 식별자로 검색 범위를 제한한다. Chroma는 임베딩과 검색을 담당하며, 원본 문서의 유일한 저장소로 사용하지 않는다.

## 3.3. MVP 범위

MVP(제품 V0.2)는 프롬프트로 입력한 코드를 대상으로 3.1의 흐름 전체를 구현한다. 범위와 구현 상세는 [SERVICE_MVP.md](SERVICE_MVP.md)를 따른다.

---

# 4. 구현 우선순위

| 단계 | 내용 | 버전 |
|---|---|---|
| **P0 — MVP 필수** | LCEL / Pydantic 구조화 출력, LangGraph 고정 Workflow, Chroma RAG, 규칙–WCAG 매핑, 정적 분석(React JSX / TSX), 개선 필요성 판단, 개선 코드 생성, 정적 재검증, 최소 Guardrails, Trace, 평가 데이터셋 | V0.2 ([SERVICE_MVP.md](SERVICE_MVP.md)) |
| **P1 — Stretch** | HTML / HTML + JS 입력 지원, ReAct 추가 조사, MCP 서버, 민감정보 Guardrails, Middleware, FastAPI, RAGAS, LLM-as-Judge, Hybrid Retrieval, Reranking | MVP 기간에 시간이 남으면 시작, V0.3에서 완성 (6장) |
| **P2 — 장기 확장** | Multi-Agent, Plan-Execute, Long-term Memory, HITL, 로컬 파일 접근·수정, 동적 분석, 코딩 Agent·CI 연동 | V0.4 이후 (7장) |

---

# 5. 제품 로드맵

| 버전 | 이름 | 내용 |
|---|---|---|
| V0.2 | Prompt-based Analysis & Improvement | **MVP.** 프롬프트로 입력한 React 코드의 정적 분석, Chroma RAG, 접근성 판단, 개선 코드 출력 ([SERVICE_MVP.md](SERVICE_MVP.md)) |
| V0.3 | Advanced Agent Workflow | HTML / HTML + JS 입력 지원. MVP에서 stretch로 남은 ReAct, MCP, RAGAS 완성. 민감정보 Guardrails, Middleware, Hybrid Retrieval, Reranking, Query Expansion |
| V0.4 | Local Project Integration | 로컬 React 프로젝트 탐색, 관련 파일 읽기, 프로젝트 지침 자동 수집 후보 생성 |
| V0.5 | Automated Code Modification | 개선 코드 Diff 생성, 사용자 승인(HITL), 실제 파일 변경, 테스트 및 롤백 |
| V0.6 | Dynamic Accessibility Analysis | Playwright 및 axe-core 기반 렌더링 검사와 키보드 상호작용 테스트 |
| V0.7 | Multi-Agent Architecture | Static Analysis / Dynamic Analysis / Knowledge / Fix Agent를 Supervisor가 조정 |
| V0.8 | Coding Agent Integration | MCP를 통해 Codex, Claude Code 등 범용 코딩 Agent에 접근성 진단 기능 제공 |
| V1.0 | Accessibility Engineering Platform | 다중 프로젝트 정책 관리, PR 리뷰, CI 연동, 검증 이력 및 접근성 품질 관리 |

MVP가 끝나면 SERVICE_MVP.md의 평가 결과와 미결정 사항 기록(`docs/decisions.md`)을 바탕으로 V0.3 범위를 확정한다.

---

# 6. P1 상세 (V0.3)

### HTML / HTML + JS 입력 지원

MVP 일정을 맞추기 위해 React만 지원하고 미룬 항목이다.

- `code_type`에 `html`, `html_js` 추가. HTML + Inline Script는 하나의 HTML 문서로 간주한다.
- 분석기: `html-validate`(a11y 규칙 프리셋). 문법 규칙도 켤지는 "새 위반" 판정에만 쓰는 방안과 함께 결정한다.
- `<script>`를 Babel Parser로 파싱하는 자체 규칙 `custom-js`

| 규칙 ID | 검출 대상 |
|---|---|
| `custom-js/click-on-non-interactive` | `getElementById` / `querySelector('#id')`로 찾은 비대화형 요소에 `click` 리스너가 있고, 키보드 리스너와 `role`·`tabindex`가 없음 |
| `custom-js/mouse-only-handler` | `mouseover` / `mouseenter` 리스너에 대응하는 `focus` 리스너가 없음 |

- 선택자를 정적으로 해석할 수 없으면 판정하지 않는다.
- 규칙–WCAG 매핑에 html-validate·custom-js 규칙을 추가하고, 재검증의 린트 우회 패턴에 `htmlvalidate-disable` 계열 주석을 추가한다.
- 평가 데이터셋에 HTML + JS 케이스(문제 있음 3, 문제 없음 1)를 추가한다.

### ReAct 추가 조사

Diagnosis 단계에서 Agent가 `search_guidelines`, `get_wcag_criterion`, `get_project_policy`를 스스로 골라 추가 조사한다. Tool 호출은 최대 4회로 제한한다. 필수 단계(정적 분석, 매핑, 재검증 등)는 계속 고정 노드로 실행한다(2.2).

### MCP 서버

로컬 MCP 서버 하나를 구성해 코드 유형 식별, 정적 분석, 근거 검색, WCAG 기준 조회, 정책 조회, 재검증을 노출한다. 내부 분석 서비스와 MCP 인터페이스는 분리하며, MCP 서버는 내부 서비스 함수를 감싸기만 하고 로직을 갖지 않는다.

### Guardrails 확장

- API 키·토큰 등 민감정보를 탐지해 LLM 전송 전에 마스킹
- 프로젝트별 지식 접근 권한 관리

### Middleware

- LLM 호출 재시도
- Tool Timeout
- 민감정보 마스킹
- Tool 호출 횟수 제한
- 입력·출력 토큰 기록
- 단계별 실행 시간 기록

### 재검증 강화

MVP에서 구현 비용 때문에 제외한 검사이다.

- 원본의 export 이름, 컴포넌트 이름, 이벤트 핸들러 식별자 보존 여부 (AST 비교)
- 추가 린트 우회 패턴
  - 키보드 핸들러 없이 `role="button"`만 추가
  - 대화형 요소나 그 조상에 `aria-hidden="true"` 추가
  - 대응하는 Finding 없이 양수 `tabIndex` 설정
- 파싱 실패한 JSX 조각을 래퍼 컴포넌트로 감싸 재파싱

### 인터페이스

- FastAPI 기반 HTTP API
- 지침 직접 입력 (`--policy-file my-guide.md`): 프로젝트 폴더를 만들지 않고 한 번만 쓰는 지침을 분석에 함께 넘긴다. 분석 시 임시 인덱싱, 프로젝트 없는 정책의 `component_mapping` 처리 방식을 함께 정해야 한다. MVP는 폴더 방식 + 자동 재인덱싱으로 대신한다(SERVICE_MVP.md 6.2).

### 평가

- RAGAS: 진단 설명과 근거에만 적용 (Faithfulness, Answer Relevancy, Context Precision, Context Recall)
- LLM-as-Judge: 진단 설명의 정확성, 개선 제안의 타당성, 코드 변경의 최소성, 출력의 이해 가능성
- 기능 유지 여부 검증: 정적 분석만으로는 한계가 있어 테스트 실행과 브라우저 자동화로 보완 (V0.6)

### 비교 평가

다음 구성을 비교해 전문 Agent가 제공하는 실질적인 추가 가치를 확인한다.

1. 범용 코딩 Agent 단독
2. 기존 정적 분석 도구
3. A11y Investigator
4. 동일한 분석 도구를 제공한 범용 코딩 Agent

### 검색 품질

- BM25 기반 키워드 검색
- Hybrid Retrieval
- Reranking
- Query Expansion
- 검색 실패 시 재검색

---

# 7. P2 상세 (V0.4 이후)

| 기술요소 | 목적 | 버전 |
|---|---|---|
| Local Filesystem Tool | 로컬 프로젝트 코드 접근 | V0.4 |
| HITL | 파일 수정 및 위험 작업 승인 | V0.5 |
| Dynamic Analysis | 브라우저 및 상호작용 검증 | V0.6 |
| Multi-Agent Supervisor | 분석·수정·검증 Agent 조정 | V0.7 |
| Plan-Execute | 다중 파일 및 프로젝트 전체 작업 | V0.7 |
| Coding Agent Integration | Codex / Claude Code 연동 | V0.8 |
| Long-term Memory | 검증된 해결 사례 및 정책 활용 | V1.0 |
| CI Integration | PR 및 빌드 파이프라인 검사 | V1.0 |

### P2 Tool

| Tool | 설명 |
|---|---|
| `read_project_file` | 로컬 파일 읽기 |
| `apply_patch` | 로컬 파일 수정 (HITL 필수) |
| `run_browser_test` | 동적 분석 |

### RAG 운영 확장

- Layer 3 Verified Cases 추가 (3.2)
- GitHub 기반 변경 감지
- Content Hash 비교 (메타데이터에 `content_hash`, `source_version` 추가)
- 변경된 청크만 재임베딩
- Source Version / Index Version 관리
- 검색 평가 후 새 인덱스 활성화
- 문서 수 증가 시 manifest를 SQLite로 이전 검토
- 서비스 운영 시 Chroma 서버 기반 배포 검토

---

# 8. 기술 방향

| 영역 | 선택 | 단계 |
|---|---|---|
| LLM / 임베딩 | AWS Bedrock (langchain-aws) | MVP |
| Agent / Workflow | LangChain, LangGraph | MVP |
| Structured Output | Pydantic | MVP |
| Backend | Python | MVP |
| Vector Database | Chroma (Local Persistent → 운영 시 서버 배포 검토) | MVP |
| 정적 분석 | Node.js 기반 ESLint + jsx-a11y (MVP), html-validate (V0.3) | MVP → V0.3 |
| Observability | LangSmith | MVP |
| Evaluation | pytest → RAGAS | MVP → V0.3 |
| API | FastAPI | V0.3 |
| MCP | MCP Python SDK | V0.3 |
| 동적 분석 | Playwright, axe-core | V0.6 |
| UI | React | 미정 |

MVP의 버전, 구성, 모델 선택 등 구체적인 결정은 [SERVICE_MVP.md](SERVICE_MVP.md) 10장과 14장을 따른다.

---

## Revision History

| 버전 | 변경 사항 |
|---|---|
| v0.1 | 최초 요구사항 및 아키텍처 정의 (SPEC.md) |
| v0.2 | React 및 HTML+JS 직접 입력 명시, 개선 코드 생성 P0 승격, 개선 후 재검증 추가, Chroma 확정, MVP Workflow 및 인수 기준 개정 |
| v0.3 | 입력·출력 사양 구체화, 정적 분석기와 Python↔Node 인터페이스 확정, 판단 규칙·재검증 기준·노드/Tool 구분 추가, 규칙–WCAG 매핑 P0 추가, 스키마 재설계, 평가 합격선 정의, 장기 계획을 ROADMAP.md로 분리 |
| v0.4 | MVP 구현 상세를 SERVICE_MVP.md로 분리하고 SPEC.md를 개요·원칙 문서로 축소 |
| **v0.5** | SPEC.md를 ROADMAP.md에 통합. 문서를 ROADMAP.md(개요·원칙·장기 계획)와 SERVICE_MVP.md(MVP 구현) 두 개로 정리. P1에 ReAct·MCP·FastAPI 설명 보강, P2 항목에 목표 버전 표시. 일정상 MVP를 React 전용으로 줄이고 HTML / HTML + JS 지원을 V0.3(6장)으로 이동 |
