# Decisions

MVP 구현 중 내린 결정과 이유를 기록한다. 항목 번호는 [SERVICE_MVP.md](../SERVICE_MVP.md) 14장의 미결정 사항을 따른다.

---

## D1. Chat LLM 모델 — 2026-11-18 확정

**결정:** `us.anthropic.claude-sonnet-4-6` (AWS Bedrock, `us-east-1`, Converse API)

- 진단 체인과 수정 체인에 모두 사용한다. temperature 0~0.2.
- 평가를 반복하는 등 비용을 줄여야 할 때는 `us.anthropic.claude-haiku-4-5-20251001-v1:0`를 보조로 쓴다.

**이유**
- 교육 과정에서 제공받은 AWS Bedrock만 쓸 수 있다.
- 계정에서 실제로 호출 가능한 모델 중 가장 성능이 높다. Claude Sonnet 5 / 5.5, Haiku 5.5, Opus 4.5 이상은 모델 목록에 보이지만 호출 권한이 없다(AccessDenied).
- 강제 Tool 호출 테스트("onClick만 있는 div는 어떤 WCAG SC 위반인가")에서 정답 `2.1.1`을 구조화 출력으로 반환했다.
- 비교: Haiku 4.5, Nova Pro, Nova Lite도 `2.1.1`로 답했고, Nova 2 Lite는 `2.4.3`(오답)으로 답했다.

## D2. 임베딩 모델 — 2026-11-18 확정

**결정:** `amazon.titan-embed-text-v2:0` (AWS Bedrock, 1024차원)

**이유**
- 계정에서 호출 가능한 다국어 임베딩 모델이 이것 하나다. Cohere Embed Multilingual v3, Cohere Embed v4는 호출 권한이 없다.
- 같은 뜻의 한국어·영어 문장 쌍의 코사인 유사도가 약 0.36으로 높지 않다. 따라서 영어 공식 문서는 영어 쿼리로 검색하고(SERVICE_MVP.md 6.5), 한국어 프로젝트 정책은 한국어로 검색하는 설계를 유지한다.
- 모델을 바꾸면 전체 재인덱싱이 필요하므로 `index_version`에 모델명을 포함한다.

## 접근 확인 방법

모델 목록(`list_foundation_models`)에 보이는 것과 실제 호출 권한은 다르다. 모델마다 최소한의 호출을 1회씩 해서 확인했다.

- Chat: Converse API + `toolChoice`로 Tool 호출을 강제한 요청 1회
- 임베딩: 한국어 문장 1개, 영어 문장 1개 임베딩

---

## 운영 메모: 리전 분리 — 2026-11-19

**상황:** `us-east-1`에서 Sonnet 4.6 호출이 `ThrottlingException: Too many tokens per day`로 거부됐다(계정 일일 토큰 한도). Haiku 4.5는 같은 시점에 호출 가능했다.

**조치**
- Chat 모델 리전을 `us-west-1`로 바꿨다(`.env`의 `AWS_DEFAULT_REGION`). 모델 ID(`us.` 추론 프로파일)는 그대로 쓴다.
- Titan Embed V2는 `us-west-1`에서 제공되지 않아(`The provided model identifier is invalid`) 임베딩 리전을 `EMBEDDING_REGION`(기본 `us-east-1`)으로 분리했다. 인덱스도 `us-east-1`에서 만들었으므로 같은 리전을 유지한다.
- 확인: 리전 변경 후 Bedrock 테스트 9개 모두 통과.

**시사점:** 일일 토큰 한도가 있으므로 T15 그래프 테스트와 T18 평가처럼 반복 실행하는 작업은 실행 횟수를 나누거나 Haiku(`light=True`)를 쓰는 방안을 D3에서 함께 정한다.

## D3. 실행당 비용·토큰 상한 — 미정 (Phase 2 시작 전)

## D4. LangSmith 사용 여부 — 미정 (Phase 2 시작 전)
