# CBNU Agent Project TODO

> 마지막 업데이트: 2026-07-06
> 다음 세션에서 이 파일을 열어 진행 상황을 확인하고 이어서 작업하세요.

---

## 진행 상태

- [x] Phase 0: 환경 세팅 (Git, .gitignore, requirements.txt, .env)
- [x] Phase 1: 데이터 수집 (4개 공지 + 기숙사 식단 크롤러)
- [ ] Phase 2: RAG 파이프라인 구축
- [ ] Phase 3: Tool 구현 (`get_dorm_menu`, `search_notices`)
- [ ] Phase 4: LangGraph 조립
- [ ] Phase 5: Middleware 및 OutputParser
- [ ] Phase 6: 문서화 및 다이어그램

---

## Phase 1 완료 내역

- 4개 공지사항 소스 크롤러 구현 완료
  - `src/crawlers/notice_crawler.py`
  - 학교 메인 학사/장학 공지
  - 전자정볼대학 공지
  - 소프트웨어학부 학부공지
  - 기숙사 공지
- 기숙사 식단 크롤러 구현 완료
  - `src/crawlers/dorm_crawler.py`
  - 개성재/양성재/양진재 오늘 메뉴
- `src/crawlers/run_all.py`로 전체 크롤링 실행 가능
- 수집 데이터:
  - `data/raw/notices/main_notice.txt`
  - `data/raw/notices/ece_notice.txt`
  - `data/raw/notices/sw_notice.txt`
  - `data/raw/notices/dorm_notice.txt`
  - `data/raw/dorm_menu/개성재.txt`
  - `data/raw/dorm_menu/양성재.txt`
  - `data/raw/dorm_menu/양진재.txt`

---

## Phase 2 시작 시 참고사항

- **백엔드 통합 원칙**: 핵심 로직은 `server.py` 하나에 작성
- RAG 인덱싱도 `server.py` 실행 시 초기화하도록 구현
- `data/raw/notices/` 아래 4개 txt 파일을 TextLoader 또는 DirectoryLoader로 로드
- `RecursiveCharacterTextSplitter`로 분할
- `Chroma` + `OpenAIEmbeddings`로 벡터스토어 구축
- `as_retriever(search_kwargs={"k": 3})`로 검색기 생성

---

## 이어서 해야 할 작업

1. `server.py` 파일 생성
2. `server.py` 상단에 설정, 상태 정의, RAG 초기화 코드 작성
3. `search_notices` Tool 구현 (RAG 검색)
4. `get_dorm_menu` Tool 구현 (식단 페이지 실시간 조회)
5. LangGraph StateGraph 구성
6. Middleware 및 OutputParser 추가
7. README 및 다이어그램 작성

---

## 알려진 이슈 / 개선 포인트

- 학교 메인 공지 본문에 상단 메뉴/네비게이션 텍스트가 많이 섞임
  - 해결 방향: 본문 영역 추출 로직 개선 또는 전처리에서 메뉴 텍스트 제거
- `python -m src.crawlers.run_all` 형태로 실행해야 함
  - `server.py` 통합 후 CLI 개선 예정
