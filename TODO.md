# CBNU Agent Project TODO

> 마지막 업데이트: 2026-07-08
> 다음 세션에서 이 파일을 열어 진행 상황을 확인하고 이어서 작업하세요.

---

## 진행 상태

- [x] Phase 0: 환경 세팅 (Git, .gitignore, requirements.txt, .env)
- [x] Phase 1: 데이터 수집 (4개 공지 + 기숙사 식단 크롤러)
- [x] Phase 2: RAG 파이프라인 구축
- [x] Phase 3: Tool 구현 (`get_dorm_menu`, `search_notices`)
- [x] Phase 4: LangGraph 조립
- [x] Phase 5: Middleware 및 OutputParser
- [x] Phase 6: 문서화 및 다이어그램

---

## 완료 내역

- Phase 2~6 모든 작업 완료
- `pytest tests/ -v` 13개 테스트 통과
- `python -m src.crawlers.run_all` 크롤링 정상 실행
- `python server.py` smoke test 통과 ("오늘 양성재 메뉴 뭐야?" → 양성재 식단 응답)
- `feature/phase-2-6` → `main` 머지 완료

---

## 향후 개선 포인트

- 학교 메인 공지 본문에 상단 메뉴/네비게이션 텍스트가 많이 섞임
  - 해결 방향: 본문 영역 추출 로직 개선 또는 전처리에서 메뉴 텍스트 제거
- `index.html`의 TODO fetch 부분을 실제 `/api/chat` 엔드포인트로 연동
- CORS 설정, 로딩/에러 상태, 모바일 반응형, 접근성 개선
- `FinalAnswer.sources`를 UI에서 링크로 노출
