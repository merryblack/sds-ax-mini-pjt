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
- `src/agent.py:NN` — 메인 에이전트 그래프
- `src/tools.py` — 도메인 도구
- `src/retriever.py` — RAG 파이프라인