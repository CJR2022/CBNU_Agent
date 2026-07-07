# CBNU Agent Project Status

> **목표**: 충북대학교 관련 정보(긱사, 학과 공지, 학생회 등)를 크롤링으로 수집하고, RAG 파이프라인을 따라 벡터스토어에 저장한 뒤, 사용자 질문에 맞는 답변을 제공하는 간단하고 직관적인 AI 에이전트를 구현한다.
>
> **최상위 지침**: 본 프로젝트는 `PLAN.md`를 최상위 기획서로, `STATUS.md`(본 파일)를 실행 상태판으로 사용한다. 새 세션에서 작업을 이어갈 때는 반드시 두 파일을 먼저 확인한다.
>
> **핵심 가치**: 복잡한 코드 없이 **코드를 볼 때마다 쉽게 이해**할 수 있도록 작성한다.

---

## 1. 진행 상태 (Phase별)

| Phase | 제목 | 상태 | 커밋 | 비고 |
|-------|------|------|------|------|
| 0 | 환경 세팅 | ✅ 완료 | - | Git, .gitignore, requirements.txt, .env |
| 1 | 데이터 수집 | ✅ 완료 | - | 4개 공지 + 기숙사 식단 크롤러 |
| 1.5 | 동적 첨부 링크 추출 개선 | ✅ 완료 | `28d45da` | Phase 2 이전에 반드시 완료 (PLAN.md §10) |
| 2 | RAG 파이프라인 구축 | ✅ 완료 | `100b1d6` → `20cff3b` | `server.py`에 DirectoryLoader → Split → Chroma |
| 3 | Tool 구현 | ✅ 완료 | `5a726db` → `ada2649` | `get_dorm_menu`, `search_notices` |
| 4 | LangGraph 조립 | ✅ 완료 | `0063a29` | StateGraph + conditional edge + MemorySaver |
| 5 | Middleware 및 OutputParser | ⏳ 진행 예정 | - | 입력 검증, 로깅, Pydantic ToolChoice |
| 6 | 문서화 및 다이어그램 | ⏳ 진행 예정 | - | README, `docs/workflow_diagram.md`, CLI 루프 |
| 7 | 최종 통합 및 main 머지 | ⏳ 진행 예정 | - | 전체 테스트, smoke test, TODO 갱신 |

---

## 2. 핵심 파일 및 역할

| 파일/디렉터리 | 역할 | 비고 |
|--------------|------|------|
| `PLAN.md` | 프로젝트 최상위 기획서 | 요구사항, 아키텍처, 평가 기준 |
| `STATUS.md` | 실행 상태판 (본 파일) | 세션 간 진행 상황 공유용 |
| `server.py` | 백엔드 전체 통합 파일 | RAG, Tool, LangGraph, Middleware, CLI |
| `src/crawlers/` | 크롤링 스크립트 | 공지사항, 기숙사 식단 |
| `data/raw/notices/` | 공지사항 원본 텍스트 | `.gitignore` 대상 |
| `data/raw/dorm_menu/` | 기숙사 식단 원본 텍스트 | `.gitignore` 대상 |
| `chroma_db/` | Chroma 벡터스토어 | `.gitignore` 대상 |
| `tests/` | 테스트 파일 | `pytest.ini`로 `pythonpath = .` 설정 |
| `.env` | API 키 등 환경변수 | `.gitignore` 대상, 절대 커밋 금지 |
| `pytest.ini` | pytest 설정 | `pythonpath = .` |

---

## 3. 현재 브랜치 및 커밋

- **작업 브랜치**: `feature/phase-2-6`
- **최신 커밋**: `0063a29` (feat: LangGraph StateGraph로 에이전트 조립)
- **베이스 브랜치**: `main`

---

## 4. 다음 세션에서 해야 할 작업

### 즉시 진행 (Task 5)
1. `server.py`에 입력 검증 미들웨어 추가 (`validate_input`)
2. `server.py`에 로깅 미들웨어 추가 (`log_middleware`)
3. Pydantic `ToolChoice` OutputParser 모델 추가
4. `middleware_node`를 StateGraph의 `START` 직후에 삽입
5. `tests/test_server.py`에 관련 테스트 추가
6. 커밋: `feat: 입력 검증 및 로깅 미들웨어, Pydantic OutputParser 추가`

### 이후 진행 (Task 6)
1. `server.py`의 `__main__`에 CLI 대화 루프 추가
2. `graph.get_graph().draw_mermaid()`로 다이어그램 생성 후 `docs/workflow_diagram.md` 저장
3. `README.md` 업데이트 (소개, 아키텍처, 설치/실행, Tool/RAG/Memory/Middleware 설명, 한계/개선)
4. 커밋: `docs: README 및 LangGraph 워크플로우 다이어그램 작성`

### 마무리 (Task 7)
1. `pytest` 전체 실행
2. `python -m src.crawlers.run_all` + `python server.py` smoke test
3. `STATUS.md` 및 `TODO.md` 완료 상태 갱신
4. `feature/phase-2-6` → `main` 머지
5. 최종 코드 리뷰

---

## 5. 알려진 이슈 / 주의사항

- `.env`의 `OPENAI_API_KEY`가 실제 OpenAI 서버에서 401 인증 오류를 반환할 수 있음.
  - 확인 방법: `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('OPENAI_API_KEY') is not None)"`
  - 키가 유효하지 않으면 LLM 호출 테스트는 skip되거나 mock으로 대첼됨.
- `data/raw/` 및 `chroma_db/`는 `.gitignore`에 포함되어 있어 커밋되지 않음.
- 모든 커밋 메시지는 한국어로 작성한다.
- 핵심 로직은 `server.py` 하나에 집중한다. `src/config.py`, `src/state.py` 등 추가 분리 금지.

---

## 6. 자주 사용하는 명령어

```bash
# 크롤링
python -m src.crawlers.run_all

# 테스트
pytest

# 에이전트 실행
python server.py

# 브랜치 상태 확인
git branch -v
git log --oneline -5
```

---

> 마지막 업데이트: 2026-07-06
