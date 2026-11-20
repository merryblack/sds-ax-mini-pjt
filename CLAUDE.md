# CLAUDE.md

A11y Investigator: React(JSX/TSX) 접근성 진단·개선 Agent (LangGraph + Bedrock + Chroma). MVP와 T21~T22까지 완료 상태다.
구조와 사용법은 [README.md](README.md), [docs/guide.md](docs/guide.md), 평가는 [docs/evaluation.md](docs/evaluation.md)를 본다. 이 파일에는 문서에 없는 작업 규칙만 둔다.

## 작업 방식
- 사용자가 "TNN 진행"이라고 하면 [TASKS.md](TASKS.md)의 해당 Task를 진행한다.
  - 끝나면 Task 제목에 `✅ 완료 (날짜)`를 붙이고 `[x]` 줄에 결과를 요약한다.
  - 한눈에 보기 표와 마일스톤도 함께 고친다.
- 새 작업은 TASKS.md에 Task를 먼저 추가한 뒤 진행한다(예: T20).
- 결정과 그 이유(모델, 방식, 합격선 조정, 보류 사항)는 [docs/decisions.md](docs/decisions.md)에 기록한다. 사용량(시간, 토큰, 비용)도 여기의 D3 표에 쌓는다.
- 명세는 [SERVICE_MVP.md](SERVICE_MVP.md), 장기 계획은 [ROADMAP.md](ROADMAP.md)다. MVP 범위를 넘는 일은 ROADMAP에 적는다.
- 사용자가 "코드나 문서는 수정하지 말고 보여만 줘"라고 하면 파일을 고치지 않는다.

## 커밋
- **커밋은 사용자가 요청할 때만 한다.** "먼저 커밋", "커밋"이 요청이다. **push는 절대 하지 않는다.**
- main에 직접 커밋한다. 메시지는 `task NN 완료 (요약)` 형식에 본문 bullet을 붙이고, 끝에 `Co-Authored-By` 줄을 넣는다.
- `git add -A`나 `git add .`를 쓰지 않는다. 이번 작업에서 만들거나 고친 파일만 지정해 스테이징한다. 무관한 파일이 섞여 들어간 적이 있다.
- amend는 사용자가 요청하고 아직 push하지 않은 경우에만 한다.

## 문서 스타일
- 문서는 한국어로 쓴다. 코드, 규칙 ID, WCAG 명칭은 원문 그대로 둔다.
- README에는 코드 줄 번호를 쓰지 않는다(계속 바뀐다).
- 바뀔 수 있는 사실(리전, 한도, 진행 상황)은 "현재 …이며 바뀔 수 있음"으로 쓴다.
- README는 절 제목만 유지하고 요약과 링크만 둔다. 상세 내용은 `docs/guide.md`(사용), `docs/evaluation.md`(평가)에 쓴다. 문서를 더 잘게 나누지 않는다.
- README "트라이앤에러 회고"에는 중요한 사례만 추가한다.
- 평가 결과는 숫자를 좋게 보이도록 다듬지 않는다. 미달, 표본 크기, 과적합 가능성을 그대로 적는다. 합격선은 사용자 동의 없이 낮추지 않는다.

## 명령

```text
python setup_env.py              # 설치 (여러 번 실행해도 안전, --yes면 인덱스까지)
python a11y.py test             # 기본. LLM 호출 없음, 약 40초. 커밋 전 전체 확인
python a11y.py test --no-node   # 개발 중 빠른 확인(약 7초), Node 분석기 테스트 제외
python a11y.py test -m llm      # Bedrock 호출 11개, 약 2~3분, 비용 발생
python a11y.py test -m eval     # 평가 실행기 1케이스, 비용 발생
python a11y.py eval             # 인-아웃 세트 30개 + RAGAS, 약 10분, 약 $1.6
python a11y.py eval --case <접두어> --no-ragas   # 일부 케이스만
python a11y.py policies check demo-ds            # 정책 형식 검증 (LLM 없음)
python a11y.py policies init <id>                # 템플릿으로 새 프로젝트 지침 폴더 생성
```

- `a11y.py`는 `.venv`의 Python으로 실행하는 런처다(`test`=pytest, `eval`=evals.evaluate, `index`=rag.ingest, `fetch`=rag.fetch, 그 외는 CLI). 문서의 사용자용 명령은 이 형식으로 쓴다(셸·OS 공통, 경로는 `/`).
- 도구로 직접 실행할 때는 `.venv/Scripts/python -m ...`도 된다. `evals` 패키지는 저장소 폴더에서 `-m`으로 실행해야 import된다.
- `setup_env.py`는 표준 라이브러리만 쓴다(시스템 Python으로 실행되므로 외부 패키지 import 금지).
- 프로젝트 지침 템플릿은 `src/a11y_investigator/templates/project-policy/`에 있다. `knowledge/project-policies/` 아래에는 템플릿을 두지 않는다(`project.yaml`이 있으면 프로젝트로 인덱싱된다).

## 비용·외부 호출
- **Bedrock을 호출하는 작업은 시작 전에 예상 시간과 비용을 사용자에게 알린다.** 대상은 `-m llm`, `-m eval`, `evals.evaluate`, CLI `analyze`다.
  - 1회 분석은 약 $0.06이다.
  - 전체 평가는 백그라운드로 실행한다. 끝나면 알림이 오니 폴링하지 않는다.
- 현재 계정에 일일 토큰 한도가 있다(`ThrottlingException`). 리전은 현재 Chat `us-west-1`, 임베딩 `us-east-1`(`EMBEDDING_REGION`)이며 바뀔 수 있다. Titan Embed V2는 인덱스를 만든 리전에서만 쓴다.
- `.env`의 AWS 키는 출력하거나 커밋하지 않는다.
- 패키지 설치는 사용자 승인 후 진행하고, `requirements.txt`에 버전을 고정한다.

## 주의할 점
- **평가 케이스(`evals/datasets/*.yaml`)**
  - `tests/test_eval_dataset.py`가 케이스 수(30개)와 카테고리 구성을 고정하고 있다. 케이스를 추가하면 이 테스트도 함께 고친다.
  - `static_rule_ids`는 실제 분석기 결과와 정확히 같아야 한다. 먼저 분석기를 돌려 확인한 뒤 라벨을 쓴다.
- **`demo-ds` 정책을 추가·수정하면 평가 라벨이 깨진다.** 기존 정책 케이스는 해당 컴포넌트에 적용되는 정책을 모두 적어 두었기 때문이다. 실험할 때는 별도 프로젝트 폴더를 쓴다.
- **프롬프트(`agent/prompts.py`)를 바꾸면 평가를 다시 돌린다.** 다만 문제 없는 코드 케이스가 적으므로 특정 케이스에 맞춰 과하게 조정하지 않는다(T19 결정).
- **테스트에서 외부 호출 함수는 모듈 이름으로 monkeypatch한다**(`nodes.analyze_code` 등). 공용 샘플은 `tests/samples.py`, 가짜 파이프라인은 `tests/fakes.py`에 있다.
- **Windows + Git Bash 환경**
  - heredoc 안의 Python 문자열에서 백슬래시(`\n`, `\a`)가 깨진 적이 있다. 긴 스크립트는 파일로 써서 실행한다.
  - 텍스트 파일은 `newline="\n"`으로 쓴다(`core.autocrlf=true`).
  - `cat > file`처럼 입력을 기다리는 명령을 실수로 넣지 않는다.
