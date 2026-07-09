# 충북대학교 AI 에이전트 기획서

> **목표**: 충북대학교 관련 흩어진 정보(긱사, 학과 공지, 학생회 등)를 크롤링으로 수집하고, RAG 파이프라인을 따라 벡터스토어에 저장한 뒤, 사용자 질문에 맞는 답변을 제공하는 간단하고 직관적인 AI 에이전트를 구현한다.
>
> **핵심 가치**: 복잡한 코드 없이 **코드를 볼 때마다 쉽게 이해**할 수 있도록 작성한다. 크롤링, RAG, LangGraph 모두 처음 접하는 학습자도 따라갈 수 있는 수준으로 단계적으로 구성한다.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | CBNU Info Agent (충북대학교 정보 통합 AI 에이전트) |
| 사용 기술 | Python 3.13, LangChain/LangGraph, OpenAI API, Chroma/FAISS, requests, BeautifulSoup4 |
| 핵심 기능 | ① 충북대 관련 웹 정보 수집 ② 벡터스토어 저장 ③ 질의응답(RAG) ④ 주제별 도구 선택 |
| 최종 산출물 | 소스코드, Workflow 다이어그램, README, requirements.txt |
| 제출 형태 | GitHub Public Repository |

---

## 2. 서비스 시나리오

> “충북대 학생이 하루에 여러 사이트(긱사, 학과, 학생회)를 돌아다니지 않고도 한 곳에서 정보를 물어볼 수 있는 챗봇”

### 대표 사용 예시

1. **긱사 메뉴 질문**
   - 사용자: "오늘 양성재 점심 메뉴 뭐야?"
   - 에이전트: `dorm_menu_tool` 호출 → 긱사 식단 페이지에서 메뉴 파싱 → 답변

2. **학사/학과 공지 질문**
   - 사용자: "컴퓨터공학과 최근 공지사항 알려줘"
   - 에이전트: `notice_search_tool` 호출 → 벡터스토어에서 검색 → 답변

3. **후속 대화**
   - 사용자: "방금 공지 중 등록금 납부 기간 자세히 알려줘"
   - 에이전트: 대화 메모리를 활용해 이전 검색 결과를 기반으로 추가 설명

---

## 3. 수집 대상 및 출처

**MVP 단계에서는 아래 4개 소스만 선정**하여 복잡도를 낮춘다. 이후 확장은 쉬운 구조로 만든다.

| 카테고리 | 사이트/게시판 | URL | 수집 방식 | 갱신 주기 | RAG/Tool |
|----------|--------------|-----|-----------|-----------|----------|
| **학교 학사/장학 공지** | 충북대학교 학사/장학 공지 | [링크](https://www.chungbuk.ac.kr/www/selectBbsNttList.do?bbsNo=8&key=815&searchCtgry=학사/장학) | requests + BeautifulSoup | 하루 1회 | RAG |
| **전자정볼대학 공지** | ECE 전자정볼대학 공지사항 | [링크](https://ece.cbnu.ac.kr/ece0602) | requests + BeautifulSoup | 하루 1회 | RAG |
| **소프트웨어학부 공지** | 소프트웨어학부 학부공지사항 | [링크](https://software.cbnu.ac.kr/sub0401) | requests + BeautifulSoup | 하루 1회 | RAG |
| **기숙사 공지** | 학생생활관 공지사항 | [링크](https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20039) | requests + BeautifulSoup | 하루 1회 | RAG |
| **기숙사 식단** | 학생생활관 오늘의 식단 | [링크](https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20041) | requests + BeautifulSoup | 식단 갱신 시(매일) | 별도 Tool |

> **원칙 1**: 크롤링이 막혀 있거나 복잡한 사이트는 일단 **샘플 HTML 파일**을 저장핸두고, 로직을 먼저 완성한 뒤 실제 URL로 교체한다.
>
> **원칙 2**: 사용자 질문이 들어올 때마다 크롤링하지 않고, **주기적으로 미리 수집**하여 벡터스토어/파일에 저장한다. 질문이 오면 저장된 데이터를 검색한다.
>
> **원칙 3**: 식단 데이터도 **RAG로 통합 검색**한다. 초기에는 별도 Tool(`get_dorm_menu`)을 두었으나, 이후 `search_notices`의 `source: dorm_menu` 필터로 통합하여 벡터스토어에서 검색하도록 개선했다.

---

## 4. 전체 아키텍처

```
┌─────────────────────────────────────┐
│        Scheduled Crawling           │  ← 주기적 크롤링 (매일 1~2회)
│   requests + BeautifulSoup          │    data/raw/ 에 저장
│                                     │
│  학교공지 + 전자정보공지 +          │
│  소프트웨어공지 + 기숙사공지          │
└───────────────┬─────────────────────┘
                ▼
┌─────────────────────────────────────┐
│           RAG Indexing              │  ← Load → Split → Embed → Store
│   TextLoader / RecursiveSplitter    │    Chroma 벡터스토어 구축
│   OpenAIEmbeddings / Chroma         │    `chroma_db/`에 영속화
└───────────────┬─────────────────────┘
                ▼
┌─────────────────┐
│   사용자 입력    │
└────────┬────────┘
         ▼
┌─────────────────┐
│   LangGraph     │  ← StateGraph 기반, 조걶 분기(conditional edge)
│   Supervisor    │    어떤 Tool을 사용할지 LLM이 판단
└────────┬────────┘
         ▼
┌──────────────────────────────────────────┐
│              Tool Router                 │
│  ┌───────────────────────────────┐       │
│  │        search_notices         │       │
│  │  (공지사항 + 기숙사 식단 통합) │       │
│  └───────────────────────────────┘       │
└────────┬────────────────────┬────────────┘
         ▼
┌──────────────────────────────────────────┐
│      Chroma Vector Store                 │
│  (4개 공지 + 기숙사 식단 통합)            │
└──────────────────────────────────────────┘
         ▼
┌──────────────────────────────────────────┐
│              Final Answer Node           │
│     (검색 결과를 바탕으로 답변 생성)       │
└──────────────────────────────────────────┘
```

### LangGraph 상태 설계

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 대화 이력
    query: str                               # 사용자 질문
    tool_name: str                           # 선택된 도구 이름
    tool_result: str                         # 도구 실행 결과
    answer: str                              # 최종 답변
```

---

## 5. 평가 요구사항 충족 방안

| 평가 항목 | 과제 요구사항 | 본 프로젝트 적용 방안 |
|-----------|---------------|----------------------|
| 개별 컴포넌트 이핏 | Message, PromptTemplate, OutputParser, Chain, Runnable 조합 | `ChatPromptTemplate`, `StrOutputParser`, `RunnableLambda` 등을 명확히 분리해 사용 |
| RAG 설계 능력 | 외부 지식 검색·활용 | `Chroma.from_documents()` → `vectorstore.as_retriever()` → RAG chain |
| 상태 및 메모리 관리 | 대화 맥락, 세션 상태 유지 | `MemorySaver` checkpointer + `messages` 상태로 멀티턴 대화 구현 |
| Agent 설계 능력 | LangGraph StateGraph, conditional edge | `add_conditional_edges()`로 도구 선택 분기 구현 |
| Middleware 활용 | 로깅, 가드레일, 예외처리 | 입력 검증 미들웨어 + 로깅 미들웨어 적용 |
| OutputParser 활용 | 구조화된 출력(JSON/Pydantic) | 도구 선택 결과를 Pydantic 모델로 파싱 |
| 실행 가능성 | requirements.txt 포함 | 모든 의존성 명시 |
| 문서화 | README, Workflow 다이어그램 | `get_graph().draw_mermaid()` 활용 |

---

## 6. 기술 스택

| 용도 | 라이브러리 | 설치 |
|------|-----------|------|
| 가상환경 | Python 3.13 venv | `python -m venv .venv` |
| LLM | `langchain-openai` | `pip install langchain-openai` |
| 코어 | `langchain-core` | `pip install langchain` |
| 그래프 | `langgraph` | `pip install langgraph` |
| 벡터스토어 | `langchain-chroma` 또는 `langchain-community` (FAISS) | `pip install langchain-chroma` |
| 임베딩 | OpenAIEmbeddings | `langchain-openai`에 포함 |
| 크롤링 | `requests`, `beautifulsoup4` | `pip install requests beautifulsoup4` |
| 환경변수 | `python-dotenv` | `pip install python-dotenv` |
| 출력 파싱 | `pydantic` | `langchain` 설치 시 포함 |

### requirements.txt 예시

```txt
langchain
langchain-openai
langgraph
langchain-chroma
requests
beautifulsoup4
python-dotenv
pydantic
```

---

## 7. 파일 구조

```
CBNU_Agent/
├── .env                      # API KEY 분리 관리 (gitignore)
├── .gitignore
├── README.md
├── PLAN.md                   # 프로젝트 기획서
├── requirements.txt
├── server.py                 # ⭐ 백엔드 전체 통합 메인 파일 (에이전트 + API)
├── src/                      # 선택적 보조 모듈 (필요한 경우만 분리)
│   ├── __init__.py
│   ├── crawlers/             # 크롤링은 별도 분리 허용 (단순 스크립트)
│   │   ├── run_all.py
│   │   ├── dorm_crawler.py
│   │   ├── notice_crawler.py
│   │   └── utils.py
│   └── (그 외 모듈은 최대한 server.py 남김)
├── data/
│   ├── raw/                  # 크롤링 원본 HTML/텍스트
│   │   ├── notices/
│   │   └── dorm_menu/
│   └── processed/            # 분할된 chunk 텍스트
├── tests/
│   └── test_server.py        # server.py 위주의 통합 테스트
└── docs/
    └── workflow_diagram.md   # LangGraph 다이어그램
```

### 백엔드 통합 원칙

- **최종 백엔드는 `server.py` 하나의 파일**로 구현한다.
- Tool 정의, RAG 체인, LangGraph 빌드, 메모리, 미들웨어, API 엔드포인트 등 핵심 로직을 모두 `server.py`에 담는다.
- **분리는 예외적으로만** 허용한다:
  - 크롤링: `src/crawlers/`에 별도 스크립트로 분리 (주기 실행용)
  - 정적 설정: API 키, URL 목록 등은 `server.py` 상단 또는 `.env`로 관리
- `src/config.py`, `src/state.py`, `src/graph/nodes.py` 등으로 나누지 않는다. 같은 맥락의 코드는 `server.py` 안에 연속해서 배치한다.
- 테스트도 `server.py`의 함수들을 직접 import해서 테스트한다.

### server.py 예상 구조

```python
# server.py
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain.tools import tool
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
import os, requests
from bs4 import BeautifulSoup

# 1. 설정
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 2. 상태 정의
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    ...

# 3. 크롤링/도구 함수
@tool
def search_notices(...): ...

# 4. RAG 초기화
retriever = build_retriever()

# 5. LangGraph 노드/엣지
def understand_node(state): ...
def route_node(state): ...
...

# 6. 그래프 빌드
graph = builder.compile(checkpointer=MemorySaver())

# 7. API/CLI 진입점
if __name__ == "__main__":
    ...
```

> **핵심**: "백엔드 진입점과 핵심 로직은 server.py 하나에서 읽힌다." 파일을 여러 개 열어다니지 않아도 전체 흐름을 파악할 수 있어야 한다.

---

## 8. 핵심 구현 개념 (학습 중심)

### 8.1 크롤링: 가장 단순한 형태

```python
import requests
from bs4 import BeautifulSoup

def fetch_html(url: str) -> BeautifulSoup:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    response.encoding = 'utf-8'
    return BeautifulSoup(response.text, "html.parser")

def fetch_dorm_menu(dorm_type: str = "1") -> str:
    """
    기숙사 식단 조회
    dorm_type: "1"=개성재, "2"=양성재, "3"=양진재
    """
    url = f"https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20041&type={dorm_type}"
    soup = fetch_html(url)
    menu = soup.select_one(".menu-table")
    return menu.get_text(strip=True) if menu else "메뉴 정보를 찾을 수 없습니다."
```

> **학습 포인트**: `requests.get()` → `encoding 설정` → `BeautifulSoup` → `select/select_one`으로 원하는 텍스트 추출.

### 8.2 공지사항 수집: 목록 + 본문

```python
def fetch_notice_list(board_url: str, base_url: str) -> list:
    """게시판 목록에서 (제목, 본문 링크) 리스트 반환"""
    soup = fetch_html(board_url)
    items = []
    for row in soup.select("table.bbs-table tbody tr"):
        a = row.select_one("a")
        if a:
            title = a.get_text(strip=True)
            href = a["href"]
            if href.startswith("/"):
                href = base_url + href
            items.append({"title": title, "url": href})
    return items

def fetch_notice_detail(url: str) -> dict:
    """공지 본문 페이지에서 제목, 날짜, 본문 추출"""
    soup = fetch_html(url)
    title = soup.select_one(".bbs-title")
    date = soup.select_one(".bbs-date")
    content = soup.select_one(".bbs-content")
    return {
        "title": title.get_text(strip=True) if title else "",
        "date": date.get_text(strip=True) if date else "",
        "content": content.get_text(strip=True) if content else "",
    }
```

### 8.3 RAG 파이프라인

```python
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# 1. Load
loader = TextLoader("data/processed/notices.txt", encoding="utf-8")
docs = loader.load()

# 2. Split
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)

# 3. Index
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=OpenAIEmbeddings(),
    persist_directory="./chroma_db"
)

# 4. Retrieve
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
```

### 8.4 Tool 정의

```python
from langchain.tools import tool

@tool
def search_notices(query: str) -> str:
    """학교/전자정보/소프트웨어/기숙사 공지사항과 기숙사 식단을 벡터 스토어에서 검색합니다.

    기숙사 식단은 `source: dorm_menu` 메타데이터로 구분되어 있어,
    메뉴/식단 질문에서는 식단 문서를 우선적으로 검색할 수 있습니다.
    """
    docs = retriever.invoke(query)
    return "\n\n".join(doc.page_content for doc in docs)
```

> **참고**: 초기 설계에서는 `get_dorm_menu`라는 별도 도구를 두었으나, 실제 구현에서 기숙사 식단을 벡터스토어에 통합 인덱싱하고 `search_notices` 하나로 공지와 식단을 모두 검색하도록 개선했다.

### 8.4 LangGraph 구조

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

builder = StateGraph(AgentState)
builder.add_node("understand", understand_node)       # 질문 분석
builder.add_node("route", route_node)                 # 도구 선택
builder.add_node("call_tool", call_tool_node)         # 도구 실행
builder.add_node("generate", generate_node)           # 답변 생성

builder.add_edge(START, "understand")
builder.add_edge("understand", "route")
builder.add_conditional_edges("route", decide_tool, {
    "dorm": "call_tool",
    "notice": "call_tool",
    "general": "generate"
})
builder.add_edge("call_tool", "generate")
builder.add_edge("generate", END)

graph = builder.compile(checkpointer=MemorySaver())
```

### 8.5 OutputParser 예시

```python
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

class FinalAnswer(BaseModel):
    answer: str = Field(description="사용자 질문에 대한 최종 답변")
    sources: list[str] = Field(description="참고한 공지/식단 URL 목록")

parser = PydanticOutputParser(pydantic_object=FinalAnswer)
```

> **참고**: 초기 설계에서는 `confidence` 필드를 포함했으나, 실제 구현에서 `answer`와 `sources`만 사용하도록 단순화했다.

> **학습 포인트**: LLM의 자유로운 텍스트 출력을 Pydantic 모델로 강제하여 답변의 일관성과 출처 추적성을 확보한다.

---

## 9. Git 관리 지침

> Git은 **"작은 단위로 자주 커밋"**하는 것이 핵심이다. 한 번에 많은 코드를 변경하면 나중에 어디서 문제가 생겼는지 찾기 어렵다.

### 9.1 커밋 단위

- **하나의 커밋에는 하나의 논리적 변경만** 담는다.
- 예: "긱사 크롤러 추가", "RAG 벡터스토어 구축", "LangGraph 조걶 분기 추가"
- 기능 추가/수정/리팩토링은 되도록 분리한다.

### 9.2 권장 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 항상 실행 가능한 안정 버전 |
| `feature/phase-X` | 각 Phase별 개발 브랜치 |
| `docs/readme` | 문서 수정 전용 브랜치 |

```bash
# Phase 1 작업 예시
git checkout -b feature/phase-1-crawling
# ... 개발 ...
git add .
git commit -m "feat: add dorm menu crawler with requests and BeautifulSoup"
git push origin feature/phase-1-crawling
```

### 9.3 커밋 메시지 컨벤션

> **모든 커밋 메시지는 한국어로 작성한다.** 변경 내용을 내가 보고 바로 이해할 수 있도록 명확하게 적는다.

```
feat:     새로운 기능 추가
fix:      버그 수정
docs:     문서 수정
test:     테스트 추가/수정
refactor: 기능 변경 없이 코드 구조 개선
chore:    설정, 의존성, 기타 잡일
```

예시:
```
feat: 4개 공지사항 크롤러 추가
fix: 공지사항 본문의 이전글/다음글 낸비게이션 텍스트 제거
docs: README 설치 방법 업데이트
```

### 9.4 .gitignore 필수 항목

```gitignore
# 가상환경
.venv/
venv/

# API 키 및 환경변수
.env

# 벡터스토어 데이터베이스 (용량 큼)
chroma_db/

# Python 캐시
__pycache__/
*.pyc
*.pyo

# 데이터 원본(선택)
# data/raw/html_backup/
```

### 9.5 커밋 전 체크리스트

- [ ] 실행 가능한 상태인가? (`python server.py` 또는 테스트 통과)
- [ ] `.env` 같은 민감 정보가 커밋에 포함되지 않았는가?
- [ ] `requirements.txt`에 새 의존성이 추가되었는가?
- [ ] 커밋 메시지가 변경 내용을 잘 설명하는가?
- [ ] 백엔드 핵심 로직이 `server.py`에 모여 있는가?

---

## 10. 단계별 구현 로드맵

> **하루~이틀 분량**으로 나누어 단계적으로 구현한다. 각 단계마다 동작을 확인한 후 다음 단계로 넘어간다.

### Phase 0: 환경 세팅 (30분)
- Python 3.13 가상환경 생성 및 활성화
- `requirements.txt` 작성 및 패키지 설치
- `.env`에 `OPENAI_API_KEY` 설정
- `.gitignore` 작성
- Git 저장소 초기화 및 첫 커밋

### Phase 1: 데이터 수집 (2~3시간)
- 4개 공지사항 게시판(학교, 전자정보, 소프트웨어, 기숙사) 목록 + 본문 크롤링
- 기숙사 식단 페이지(개성재/양성재/양진재) 샘플 크롤링
- 수집 결과를 `data/raw/notices/` 및 `data/raw/dorm_menu/`에 저장
- **`src/crawlers/run_all.py` 작성**: 전체 크롤링을 한 번에 실행
- **학습 포인트**: requests + BeautifulSoup 기본 문법 익히기

> **Phase 1 → Phase 2 넘어가기 전에 반드시 해결할 것**  
> 현재 `_extract_attachments()`는 `.pdf`, `.hwp` 등 확장자로 끝나는 링크만 추출하는데, 학교 메인/ECE/SW/기숙사 첨부파일 링크는 대부분 `downloadBbsFile.do?atchmnflNo=...`처럼 동적 다운로드 URL이다. 따라서 **Phase 2 RAG 파이프라인을 시작하기 전에 `_extract_attachments()`를 개선하여 동적 다운로드 링크도 추출**해야 한다. 본문이 이미지로 된 공지의 경우 PDF 첨부 텍스트 추출이 중요하므로, 이 작업을 먼저 끝낸 뒤 Phase 2로 진행한다.

### Phase 2: RAG 파이프라인 구축 (2~3시간)
- `server.py` 안에서 `data/raw/notices/` 아래 텍스트 파일들을 로드
- `server.py` 안에서 `RecursiveCharacterTextSplitter`로 분할
- `server.py` 안에서 Chroma 벡터스토어에 저장
- `server.py` 안에 `retriever` 객체를 전역 또는 함수로 구성
- `as_retriever()`로 검색 테스트
- **학습 포인트**: Load → Split → Index → Retrieve 흐름 이해

### Phase 3: Tool 구현 (1~2시간)
- `server.py` 안에서 `@tool` 데코레이터로 `search_notices` 도구를 구현한다.
- 공지 검색 도구: Chroma 벡터스토어에서 검색한다.
- 기숙사 식단도 `search_notices`의 `source: dorm_menu` 필터로 검색할 수 있도록 한다.
- 각 도구 개별 테스트

> **참고**: 초기 기획에서는 `get_dorm_menu`라는 별도 긱사 메뉴 도구를 두었으나, 이후 식단 데이터를 벡터스토어에 통합하고 `search_notices` 하나로 통합 검색하도록 개선했다.

### Phase 4: LangGraph 조립 (2~3시간)
- `server.py` 안에서 `AgentState` 정의
- `server.py` 안에 middleware → understand → route → call_tool → generate 노드 구현
- `add_conditional_edges`로 도구/일반 분기 및 middleware 검증 실패 분기 구현
- `MemorySaver`로 대화 이력 유지
- **학습 포인트**: StateGraph, Node, Edge, checkpointer

### Phase 5: Middleware 및 OutputParser (1~2시간)
- `server.py` 안에서 입력 검증 미들웨어 추가
- `server.py` 안에서 로깅 미들웨어 추가
- `generate_node`에서 Pydantic OutputParser(`FinalAnswer`)로 최종 답변 구조화

### Phase 6: 문서화 및 다이어그램 (1시간)
- `server.py`에서 `graph.get_graph().draw_mermaid()`로 워크플로우 다이어그램을 생성한다.
- 생성한 Mermaid 다이어그램을 `README.md`의 아키텍처 설명 섹션에 직접 병합한다.
- README 작성
  - 서비스 소개 및 사용 시나리오
  - 전체 아키텍처 설명 (다이어그램 포함)
  - 설치 및 실행 방법 (`python server.py`)
  - 사용된 Tool / RAG / Memory / Middleware / OutputParser 설명
  - 한계점 및 향후 개선 방향
- Chroma 벡터스토어는 `chroma_db/`에 영속화하며, 실행 시 기존 컬렉션이 있으면 로드한다.
- `main` 브랜치에 최종 머지 및 GitHub에 푸시

---

## 11. 데이터 갱신 흐름 요약

```
[1단계: 크롤링]
python -m src.crawlers.run_all
→ data/raw/ 에 HTML/텍스트 저장

[2단계: 인덱싱]
python server.py  # 실행 시 자동으로 벡터스토어 초기화
→ chroma_db/ 에 벡터스토어 생성

[3단계: 대화]
python server.py
→ 사용자 질문 → LangGraph → 도구 선택 → 저장된 데이터 검색/조회 → 답변 생성
```

---

## 12. 예상 질문 유형 및 처리 흐름

| 사용자 질문 | 판단 | 호출 도구 | 답변 방식 |
|-------------|------|-----------|-----------|
| "오늘 양성재 메뉴 뭐야?" | 도메인: 긱사 | `search_notices` | 기숙사 식단 벡터스토어 검색 |
| "기숙사 입퇴거 날짜 알려줘" | 도메인: 공지 | `search_notices` | 기숙사 공지 RAG 검색 |
| "컴공 학사공지 중 등록금 관련 있어?" | 도메인: 공지 | `search_notices` | RAG 검색 결과 기반 답변 |
| "전자정볼대학 장학 공지 있어?" | 도메인: 공지 | `search_notices` | RAG 검색 결과 기반 답변 |
| "안녕?" | 일반 대화 | `general` | LLM이 직접 답변 |
| "방금 메뉴 중 점심만 다시 알려줘" | 후속 질문 | 메모리 활용 | 이전 대화 참고 |

---

## 13. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 크롤링 차단 | 샘플 HTML을 `data/raw/`에 저장핸두고 로직 완성 후 실제 URL 적용 |
| 웹사이트 구조 변경 | CSS 선택자를 `config.py`에 분리해 쉽게 교체 가능하도록 설계 |
| API 비용 | `gpt-4o-mini` 사용, chunk 크기와 검색 개수(k) 제한 |
| 복잡한 코드 | 함수 하나에 한 가지 책임만 부여, 파일 분리 |
| 실시간성 부족 | 필요시 수동으로 `run_all.py` 실행하여 즉시 갱신 |

---

## 14. 산출물 체크리스트

- [ ] GitHub Public Repository 생성
- [ ] `requirements.txt` 포함
- [ ] `.env`로 API Key 분리 관리
- [ ] 주기적 크롤링 스크립트 (`src/crawlers/run_all.py`)
- [ ] 벡터스토어 인덱싱 로직 (`server.py` 내 포함)
- [x] Tool 구현 (`search_notices`로 공지 + 식단 통합 검색)
- [ ] `server.py`에 백엔드 핵심 로직 집중
- [ ] 4개 공지 소스 수집 (학교, 전자정보, 소프트웨어, 기숙사)
- [ ] RAG 파이프라인 1개 이상 포함
- [ ] 대화 메모리(`MemorySaver`) 적용
- [ ] LangGraph `StateGraph` + `conditional edge` 적용
- [ ] Middleware 1개 이상 적용 (로깅/입력검증)
- [ ] OutputParser(Pydantic) 적용
- [x] Workflow 다이어그램 포함 (README에 Mermaid로 병합)
- [ ] README 작성 (서비스 소개, 아키텍처, 설치/실행, 기술 설명, 한계/개선)
- [ ] Git 커밋 이력이 Phase별로 정리되어 있음
- [ ] 최종 코드가 `main` 브랜치에 머지됨

---

## 15. 결론

이 프로젝트는 **주기적 크롤링 → RAG 인덱싱 → LangGraph Agent**로 이어지는 전형적인 AI 에이전트 흐름을, 최소한의 코드와 직관적인 구조로 경험하는 것이 목표다. 복잡한 멀티에이전트나 고급 기능은 일단 제외하고, **동작하는 최소 단위(MVP)**를 먼저 만들고 점진적으로 확장한다.

> **아키텍처 개선 이력**: 초기 기획에서는 기숙사 식단을 실시간으로 조회하는 별도 도구(`get_dorm_menu`)를 사용했으나, 이후 기숙사 식단 데이터를 공지사항과 동일한 Chroma 벡터스토어에 인덱싱하고 `search_notices` 하나로 통합 검색하도록 개선했다. 또한 벡터스토어를 `chroma_db/`에 영속화하여 실행 시 임베딩 비용을 줄이고, `FinalAnswer`는 `answer`와 `sources`만 남기도록 단순화했다.

다음 단계는 Phase 0부터 한 단계씩 코드로 옮기는 구현이다.
