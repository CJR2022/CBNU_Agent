# CBNU Agent Project TODO

> 마지막 업데이트: 2026-07-09
> 다음 세션에서 이 파일을 열어 진행 상황을 확인하고 이어서 작업하세요.

---

## 진행 상태

- [x] Phase 0: 환경 세팅 (Git, .gitignore, requirements.txt, .env)
- [x] Phase 1: 데이터 수집 (4개 공지 + 기숙사 식단 크롤러)
- [x] Phase 2: RAG 파이프라인 구축
- [x] Phase 3: Tool 구현 (`search_notices`, 식단 통합)
- [x] Phase 4: LangGraph 조립
- [x] Phase 5: Middleware 및 OutputParser
- [x] Phase 6: 문서화 및 다이어그램 (README에 병합)
- [x] 공지사항 일반 공지 최신 50개까지 페이지 순회 수집
- [x] Chroma 벡터스토어 영속화 (`chroma_db/`)
- [x] 기숙사 식단을 벡터스토어로 통합 및 `get_dorm_menu` 제거
- [x] `search_notices` 출처/날짜 필터링 및 fallback 개선
- [x] `FinalAnswer`에서 `confidence` 필드 제거
- [x] `understand_node` 출처/날짜/기숙사 키워드 보정

---

## 완료 내역

- Phase 0~6 모든 작업 완료
- `pytest tests/ -v` 13개 테스트 통과
- `python -m src.crawlers.run_all` 크롤링 정상 실행
- `python server.py` smoke test 통과
- `feature/phase-2-6` → `main` 머지 완료
- 공지사항 페이지 순회 수집 및 중복 제거 개선
- Chroma 벡터스토어 영속화 및 크롤링 시 재빌드
- 식단 데이터 벡터스토어 통합
- API 응답 구조 단순화 (`answer`, `sources`)

---

## 향후 개선 포인트

- **학교 메인 공지 본문 전처리**: 학교 메인 공지 본문 상단에 메뉴/네비게이션 텍스트가 많이 섞임
  - 해결 방향: 본문 영역 추출 로직 개선 또는 전처리에서 메뉴 텍스트 제거
- **자동 크롤링 스케줄러**: GitHub Actions 등으로 주기적 수집 자동화
- **추가 데이터 소스**: 학생회, 장학 공지, 도서관 등 확장
- **평가 및 추적**: LangSmith 등으로 LLM 호출과 검색 품질 모니터링
- **브랜치 정리**: `feature/phase-2-6` 브랜치 검토 및 병합/삭제
- **미커밋 변경 처리**: `server.py`의 uncommitted 변경사항 검토 및 커밋
