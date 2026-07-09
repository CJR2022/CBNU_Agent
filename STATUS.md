# CBNU Agent Project Status

> **목표**: 충북대학교 관련 정보(긱사, 학과 공지, 학생회 등)를 크롤링으로 수집하고, RAG 파이프라인을 따라 벡터스토어에 저장한 뒤, 사용자 질문에 맞는 답변을 제공하는 간단하고 직관적인 AI 에이전트를 구현한다.
>
> **최상위 지침**: 본 프로젝트는 `PLAN.md`를 최상위 기획서로, `STATUS.md`(본 파일)를 실행 상태판으로 사용한다. 새 세션에서 작업을 이어갈 때는 반드시 두 파일을 먼저 확인한다.
>
> **핵심 가치**: 복잡한 코드 없이 **코드를 볼 때마다 쉽게 이해**할 수 있도록 작성한다.

---

## 1. 진행 상태 (Phase별)

| Phase | 제목 | 상태 | 비고 |
|-------|------|------|------|
| 0 | 환경 세팅 | ✅ 완료 | Git, .gitignore, requirements.txt, .env |
| 1 | 데이터 수집 | ✅ 완료 | 4개 공지 + 기숙사 식단 크롤러 |
| 1.5 | 동적 첨부 링크 추출 개선 | ✅ 완료 | Phase 2 이전에 반드시 완료 (PLAN.md §10) |
| 2 | RAG 파이프라인 구축 | ✅ 완료 | `server.py`에 DirectoryLoader → Split → Chroma |
| 3 | Tool 구현 | ✅ 완료 | `search_notices` (식단 통합) |
| 4 | LangGraph 조립 | ✅ 완료 | StateGraph + conditional edge + MemorySaver |
| 5 | Middleware 및 OutputParser | ✅ 완료 | 입력 검증, 로깅, Pydantic FinalAnswer |
| 6 | 문서화 및 다이어그램 | ✅ 완료 | README에 워크플로우 다이어그램 병합 |
| 7 | 최종 통합 및 main 머지 | ✅ 완료 | 전체 테스트, smoke test, `feature/phase-2-6` → `main` |
| 8 | 개선 작업 (메타데이터 검색 / PDF / 환각 방지) | ✅ 완료 | 공지 메타데이터 기반 검색, PDF 첨부 내용 포함, 환각 방지 개선 |
| 9 | 추가 개선 | ✅ 완료 | 공지 50개 페이지 순회, Chroma 영속화, 식단 통합, confidence 제거 |

---

## 2. 핵심 파일 및 역할

| 파일/디렉터리 | 역할 | 비고 |
|--------------|------|------|
| `PLAN.md` | 프로젝트 최상위 기획서 | 요구사항, 아키텍처, 평가 기준 |
| `STATUS.md` | 실행 상태판 (본 파일) | 세션 간 진행 상황 공유용 |
| `README.md` | 사용자/개발자 안내 문서 | 실행 방법, 아키텍처, 기술 설명, 한계/개선 |
| `TODO.md` | 할 일 및 완료 내역 | 세션 간 우선순위 공유용 |
| `server.py` | 백엔드 전체 통합 파일 | RAG, Tool, LangGraph, Middleware, API 함수 |
| `src/crawlers/` | 크롤링 스크립트 | 공지사항, 기숙사 식단 |
| `data/raw/notices/` | 공지사항 원본 텍스트 | `.gitignore` 대상 |
| `data/raw/dorm_menu/` | 기숙사 식단 원본 텍스트 | `.gitignore` 대상 |
| `chroma_db/` | Chroma 벡터스토어 | `.gitignore` 대상, 영속화됨 |
| `tests/` | 테스트 파일 | `pytest.ini`로 `pythonpath = .` 설정 |
| `.env` | API 키 등 환경변수 | `.gitignore` 대상, 절대 커밋 금지 |
| `pytest.ini` | pytest 설정 | `pythonpath = .` |

---

## 3. 현재 브랜치 및 커밋

- **작업 브랜치**: `main`
- **최신 커밋**: `ce6dd24` (`fix: placeholder-like chunk가 실제 본문 chunk를 가리던 문제 해결`)
- **작업 중인 변경**: 없음 (working tree clean)
- **참고 브랜치**: `feature/phase-2-6`는 현재 `main`보다 뒤쳐진 상태. 병합/삭제 검토 필요.

---

## 4. 개선 작업 완료 내용

### 4.1 공지 메타데이터 기반 검색
- `build_retriever()`에서 각 `.txt` 파일을 개별 공지로 분리하고 `title`, `date`, `url` 메타데이터를 추출한다.
- 날짜는 가능하면 `YYYY-MM-DD`로 파싱하고, 불가능하면 원본 문자열을 유지한다.
- `RecursiveCharacterTextSplitter`로 분할 후 각 chunk 앞에 `[공지사항] 제목/날짜/URL` 헤더를 추가한다.
- `search_notices()`에서 "최근", "최신" 키워드가 포함된 질문은 날짜 기준 내림차순 정렬 후 상위 5개를 반환한다.

### 4.2 PDF 첨부 내용 포함
- `src/crawlers/notice_crawler.py`의 `_extract_attachments()`는 정적 확장자뿐 아니라 `downloadBbsFile.do?atchmnflNo=...`, `fileNo=...` 형태의 동적 다운로드 링크도 추출한다.
- 본문이 100자 미만인 공지에서 동적 다운로드 링크도 PDF로 추출하여 내용을 보강한다.

### 4.3 환각 방지
- `generate_node` 시스템 프롬프트에 "검색된 정보에 없는 내용은 지어내지 말 것", "근거가 부족하면 학교 홈페이지 확인 안내" 지침을 추가했다.
- `search_notices()`에서 관련 결과를 찾지 못하면 "관련 공지를 찾을 수 없습니다"를 반환한다.
- `generate_node`에서 최종 답변에 실제로 등장하는 URL만 `sources`로 유지한다.

### 4.4 chunk 선택 개선
- `_collect()`에서 제목/메타데이터만 담긴 placeholder-like chunk를 스킵한다.
- 같은 URL의 여러 chunk 중 실제 본문이 담긴 **가장 긴 chunk를 우선 선택**한다.
- "자세히", "상세히" 키워드가 있으면 같은 공지의 chunk를 최대 3개까지 반환한다.

### 4.5 추가 개선 사항
- **공지 페이지 순회 수집**: 일반 공지를 최신 50개까지 페이지를 순회하며 수집한다.
- **상단 고정 공지 중복 제거**: 고정 공지와 일반 공지 간 중복을 제거하고, URL 중복도 방지한다.
- **Chroma 벡터스토어 영속화**: `chroma_db/`에 저장된 컬렉션이 있으면 로드하고, 크롤링 실행 시에만 `force_rebuild=True`로 갱신한다.
- **식단 데이터 통합**: 기숙사 식단을 별도 도구가 아닌 `search_notices`의 `source: dorm_menu` 필터로 검색한다. 초기 `get_dorm_menu` 도구는 제거되었다.
- **`confidence` 필드 제거**: `FinalAnswer`와 API 응답에서 `confidence` 필드를 제거하고, `answer`와 `sources`만 사용한다.
- **출처 키워드 보정**: `understand_node`에서 사용자가 언급한 출처(기숙사/전자정보/소프트웨어/학교)와 날짜/기숙사 이름이 `search_notices`의 `query`에 누락되지 않도록 보정한다.

---

## 5. 다음 세션에서 해야 할 작업

모든 예정된 Phase 및 개선 작업이 완료되었습니다. 향후 작업은 선택 사항입니다.

### 선택적 개선 포인트
1. **자동 크롤링 스케줄러**: GitHub Actions 등으로 주기적으로 공지사항을 수집하도록 자동화.
2. **추가 데이터 소스**: 학생회, 장학 공지, 도서관 등 정보 확장.
3. **본문 전처리 강화**: 학교 메인 공지 본문의 상단 메뉴/네비게이션 텍스트 제거.
4. **평가 및 추적**: LangSmith 등으로 LLM 호출과 검색 품질 모니터링.
5. **브랜치 정리**: `feature/phase-2-6` 브랜치 검토 및 삭제.

---

## 6. 알려진 이슈 / 주의사항

- `.env`의 `OPENAI_API_KEY`가 실제 OpenAI 서버에서 401 인증 오류를 반환할 수 있음.
  - 확인 방법: `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('OPENAI_API_KEY') is not None)"`
  - 키가 유효하지 않으면 LLM 호출 테스트는 skip되거나 mock으로 대첻됨.
- `OPENAI_API_KEY`는 `load_dotenv()`로 환경변수에 로드되므로, `ChatOpenAI()`/`OpenAIEmbeddings()`에 별도로 전달할 필요가 없음.
- `data/raw/` 및 `chroma_db/`는 `.gitignore`에 포함되어 있어 커밋되지 않음.
- 모든 커밋 메시지는 한국어로 작성한다.
- 핵심 로직은 `server.py` 하나에 집중한다. `src/config.py`, `src/state.py` 등 추가 분리 금지.

---

## 7. 자주 사용하는 명령어

```bash
# 크롤링
python -m src.crawlers.run_all

# 테스트
pytest

# 웹 서버 실행
uvicorn server:app --reload

# 브랜치 상태 확인
git branch -v
git log --oneline -5
```

---

> 마지막 업데이트: 2026-07-10
