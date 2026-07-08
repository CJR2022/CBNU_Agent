# CBNU Agent

충북대학교 관련 정보(기숙사 식단, 학과 공지, 학교 공지 등)를 한 곳에서 물어볼 수 있는 간단한 AI 챗봇 에이전트입니다.

## 1. 서비스 소개 및 사용 시나리오

"충북대 학생이 하루에 여러 사이트를 돌아다니지 않고도 한 곳에서 정보를 물어보는 챗봇"을 목표로 합니다.

### 대표 사용 예시

- **기숙사 식단 질문**
  - 사용자: "오늘 양성재 점심 메뉴 뭐야?"
  - 에이전트: 기숙사 식단 페이지를 실시간으로 조회해서 답변합니다.

- **학사/학과 공지 질문**
  - 사용자: "컴퓨터공학과 최근 공지사항 알려줘"
  - 에이전트: 미리 수집한 공지사항 데이터에서 검색해서 답변합니다.

- **후속 대화**
  - 사용자: "방금 공지 중 등록금 납부 기간 자세히 알려줘"
  - 에이전트: 대화 메모리를 활용해 이전 검색 결과를 기반으로 추가 설명합니다.

## 2. 전체 아키텍처 설명

```
사용자 입력
    ↓
middleware (입력 검증 + 로깅)
    ↓
understand_node (도구 선택/일반 대화 판단)
    ↓ (조건 분기)
call_tool_node ────────→ generate_node
    ↓                        ↓
기숙사 식단/공지 검색       최종 답변 생성
```

- **LangGraph** 기반의 `StateGraph`로 동작하며, `MemorySaver`를 사용해 대화 맥락을 유지합니다.
- 입력은 `middleware`에서 검증되고, 질문 유형에 따라 도구를 호출하거나 바로 답변을 생성합니다.
- 전체 워크플로우 다이어그램은 [docs/workflow_diagram.md](docs/workflow_diagram.md)에서 확인할 수 있습니다.

## 3. 설치 및 실행 방법

### 1) 의존성 설치

```bash
pip install -r requirements.txt
```

### 2) 환경 변수 설정

`.env.example`을 참고해 `.env` 파일을 만들고 OpenAI API 키를 입력합니다.

```bash
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY를 입력합니다.
```

```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3) 에이전트 실행

```bash
python server.py
```

`index.html`은 브라우저에서 직접 열어 웹 UI 데모를 확인할 수 있습니다.

### 웹 UI로 실행

```bash
uvicorn server:app --reload
```

브라우저에서 http://localhost:8000 열기

실행하면 아래와 같이 대화형 프롬프트가 표시됩니다.

```text
충북대학교 정보 안내 챗봇 CBNU Agent에 오신 것을 환영합니다!
종료하려면 'exit', 'quit' 또는 '종료'를 입력하세요.

사용자: 안녕?
에이전트: 안녕하세요! 충북대학교 정보 안내 챗봇입니다.
```

## 4. 사용된 주요 기술

### Tool

- `get_dorm_menu(dorm_name: str)`: 충북대 기숙사 식단 페이지에서 오늘 날짜의 식단을 실시간으로 가져옵니다.
- `search_notices(query: str)`: 미리 구축한 Chroma 벡터스토어에서 사용자 질문과 관련된 공지 내용을 검색합니다.

### RAG

- `data/raw/notices/`에 있는 텍스트 파일들을 `DirectoryLoader`로 읽고, `RecursiveCharacterTextSplitter`로 분할합니다.
- `OpenAIEmbeddings`로 임베딩한 뒤 `Chroma` 벡터스토어에 저장합니다.
- 질문이 들어오면 `retriever.invoke(query)`로 유사도 기반 문서를 검색해 답변에 활용합니다.

### Memory

- `langgraph.checkpoint.memory.MemorySaver`를 사용해 스레드별 대화 이력을 유지합니다.
- 이전 대화 맥락을 바탕으로 후속 질문에 자연스럽게 답변할 수 있습니다.

### Middleware

- `middleware_node`는 사용자 입력이 비어 있거나 1000자를 초과하는지 검증합니다.
- 유효하지 않은 입력은 바로 안내 메시지를 반환하고 워크플로우를 종료합니다.
- `log_middleware`에서는 최신 사용자 메시지와 메시지 개수를 로깅합니다.

### OutputParser

- `FinalAnswer` Pydantic 모델을 정의해 최종 답변을 `answer`와 `sources` 필드로 구조화합니다.
- `generate_node`에서 LLM 출력을 파싱해 깔끔한 답변을 생성합니다.

### 웹 UI

- 프로젝트 루트에 있는 `index.html`은 단일 파일로 구성된 반응형 채팅 UI입니다.
- 현재는 정적 템플릿이며, 향후 `/api/chat` 엔드포인트와 연결해 `run_agent()`를 호출할 예정입니다.
- 브라우저에서 `index.html` 파일을 직접 열어볼 수 있으며, UI 데모를 확인할 수 있습니다.

## 5. 한계점 및 향후 개선 방향

### 한계점

- **실시간 데이터 의존**: 공지사항은 주기적 크롤링 이후에 검색할 수 있어 최신 글이 바로 반영되지 않을 수 있습니다.
- **크롤링 불안정성**: 웹사이트 구조가 변경되면 CSS 선택자를 직접 수정해야 합니다.
- **출처 표시**: RAG 검색 결과에서 참고한 원본 URL을 답변에 명확히 포함하는 기능이 추가로 필요합니다.

### 향후 개선 방향

- **자동 크롤링 스케줄러**: GitHub Actions 등으로 주기적으로 공지사항을 수집하도록 자동화합니다.
- **더 많은 데이터 소스**: 학생회, 장학 공지, 도서관 등 추가 정보를 확장합니다.
- **웹/모바일 인터페이스**: CLI뿐 아니라 Streamlit, 웹 API 등 다양한 진입점을 제공합니다.
- **평가 및 추적**: LangSmith 등으로 LLM 호출과 검색 품질을 모니터링합니다.
