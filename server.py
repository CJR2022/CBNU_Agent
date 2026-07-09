"""CBNU Agent RAG 서버 모듈.

LangGraph 기반 에이전트를 구성하며, middleware 노드, 도구 노드, 그리고
대화형 CLI와 `run_agent()` API 진입점을 제공합니다.

주요 구성 요소:
- LangGraph `StateGraph`: middleware → understand → tool/generate 워크플로우
- `middleware_node`: 입력 검증 및 로깅
- `search_notices`: 공지사항 및 기숙사 식단 검색 도구
- `run_cli()`: 터미널 대화형 CLI
- `run_agent()`: HTML UI 및 API 서버에서 호출하는 순수 함수형 진입점
"""

import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Literal

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FinalAnswer(BaseModel):
    """최종 답변을 구조화하는 Pydantic OutputParser 모델."""

    answer: str = Field(description="사용자 질문에 대한 최종 답변. 검색된 정보만 사용하고, 정보가 없으면 '해당 정보는 확인할 수 없습니다'라고 답변하세요.")
    sources: list[str] = Field(description="참고한 공지/식단 URL 목록")
    confidence: Literal["high", "medium", "low"] = Field(description="답변 확신도: high, medium, low 중 하나. 근거가 충분하면 high, 부족하면 low")


def fetch_html(url: str) -> BeautifulSoup:
    """주어진 URL의 HTML을 요청하고 BeautifulSoup 객체를 반환한다."""
    headers = {"User-Agent": "Mozilla/5.0 (CBNU-Agent/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.encoding = "utf-8"
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


_SOURCE_KEYWORDS = {
    "dorm": ["기숙사", "생활관"],
    "ece": ["전자정보"],
    "sw": ["소프트웨어", "컴공"],
    "main": ["학교", "학사", "본교"],
}

_MEAL_KEYWORDS = ["메뉴", "식단", "아침", "점심", "저녁", "밥"]


def _is_meal_query(query: str) -> bool:
    """query에서 식단/메뉴 관련 키워드를 감지한다."""
    return any(keyword in query for keyword in _MEAL_KEYWORDS)


def _detect_sources(query: str, include_menu: bool = False) -> list[str]:
    """query에서 공지 출처 키워드를 감지하면 source 이름 목록을 반환한다."""
    sources = set()
    for source, keywords in _SOURCE_KEYWORDS.items():
        if any(keyword in query for keyword in keywords):
            sources.add(source)
    if include_menu:
        sources.add("dorm_menu")
    return sorted(sources)


def _source_injection_keyword(source: str) -> str:
    """source 이름을 search_notices query에 주입할 키워드로 변환한다."""
    if source == "dorm_menu":
        return "기숙사"
    return _SOURCE_KEYWORDS[source][0]


# 단순 질문/어미는 확장 시 제거하여 핵심 키워드만 남긴다.
_QUESTION_STOPWORDS = {
    "언제", "어디", "무엇", "뭐", "있어", "있나요", "있습니까",
    "알려줘", "알려주세요", "해줘", "해주세요", "말해줘", "가르쳐줘",
    "줘", "해", "돼", "되나요", "인가요",
}


def _expand_query(query: str, kst: datetime | None = None) -> list[str]:
    """짧고 구체적인 질문에 대해 검색 변형을 생성한다.

    예: "기숙사 생활관비 납부 언제까지야?" ->
        ["기숙사 생활관비 납부", "생활관비 납부", "기숙사 생활관비 납부 기간", ...]
    """
    if kst is None:
        kst = datetime.now(timezone(timedelta(hours=9)))

    clean = re.sub(r"[?？!！.,]+$", "", query).strip()
    words = [w for w in clean.split() if w not in _QUESTION_STOPWORDS]
    if len(words) < 2:
        variations = [clean]
    else:
        variations = [clean]

        # 연속된 2~3단어 조합 추가
        for i in range(len(words) - 1):
            variations.append(" ".join(words[i : i + 2]))
        for i in range(len(words) - 2):
            variations.append(" ".join(words[i : i + 3]))

        # 날짜/기간 관련 질문에는 명시적 기간 키워드 추가
        if any(w in query for w in ("언제", "기간", "날짜", "마감", "까지", "입퇴거")):
            base = " ".join(words)
            if "기간" not in base:
                variations.append(f"{base} 기간")
            if "날짜" not in base:
                variations.append(f"{base} 날짜")

    # 오늘/어제/내일/이번 주/다음 주 키워드를 절대 날짜로 변환
    if "오늘" in query:
        variations.append(kst.date().isoformat())
    if "어제" in query:
        variations.append((kst.date() - timedelta(days=1)).isoformat())
    if "내일" in query:
        variations.append((kst.date() + timedelta(days=1)).isoformat())
    if "이번 주" in query:
        start = kst.date() - timedelta(days=kst.date().weekday())
        for i in range(7):
            variations.append((start + timedelta(days=i)).isoformat())
    if "다음 주" in query:
        start = kst.date() + timedelta(days=7 - kst.date().weekday())
        for i in range(7):
            variations.append((start + timedelta(days=i)).isoformat())

    # 중복 제거하면서 순서 유지
    seen = set()
    result = []
    for v in variations:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


@tool
def search_notices(query: str) -> str:
    """학교/전자정보/소프트웨어/기숙사 공지사항과 기숙사 식단을 벡터 스토어에서 검색한다.

    Args:
        query: 검색할 키워드나 문장.

    Returns:
        검색된 공지/식단 내용을 두 줄 개행으로 연결한 문자열.
    """
    kst = datetime.now(timezone(timedelta(hours=9)))
    is_meal = _is_meal_query(query)
    sources = _detect_sources(query, include_menu=is_meal)

    queries = _expand_query(query, kst)

    docs: list[Document] = []
    seen_urls = set()

    if is_meal:
        # 식단 질문은 dorm_menu를 우선적으로 검색한다.
        for q in queries:
            for doc in retriever.invoke(q):
                if doc.metadata.get("source") == "dorm_menu":
                    url = doc.metadata.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        docs.append(doc)
        # 식단 결과가 없으면 기숙사 공지로 fallback
        if not docs:
            for q in queries:
                for doc in retriever.invoke(q):
                    if doc.metadata.get("source") == "dorm":
                        url = doc.metadata.get("url")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            docs.append(doc)
    else:
        for q in queries:
            for doc in retriever.invoke(q):
                url = doc.metadata.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    docs.append(doc)

        if sources:
            docs = [doc for doc in docs if doc.metadata.get("source") in sources]

    recent_keywords = ["최근", "최신"]
    if any(keyword in query for keyword in recent_keywords):
        if sources:
            docs = [doc for doc in docs if doc.metadata.get("source") in sources]
        docs = sorted(docs, key=_sort_key, reverse=True)[:5]
    else:
        docs = docs[:10]

    if not docs:
        return "관련 공지를 찾을 수 없습니다."

    return "\n\n".join(doc.page_content for doc in docs)


def _sort_key(doc: Document):
    """문서를 날짜 기준으로 정렬하기 위한 키 함수."""
    date_str = doc.metadata.get("date", "")
    try:
        return (True, date.fromisoformat(date_str), date_str)
    except Exception:
        return (False, date.min, date_str)


def _source_name_from_path(path: str) -> str:
    """공지 파일 경로에서 소스 이름(main/ece/sw/dorm)을 추출한다."""
    return path.replace("\\", "/").split("/")[-1].split("_")[0]


def _split_into_notices(page_content: str) -> list[str]:
    """하나의 .txt 파일에 포함된 여러 공지를 분리한다."""
    # 파일 상단의 '# {source} 공지사항' 헤더는 첫 공지에 포함되도록 제거
    content = re.sub(r"^#\s+.+\n+", "", page_content.strip(), count=1)
    # '==========' 형태의 구분선으로 공지 분리
    parts = re.split(r"\n={10,}\n", content)
    return [part.strip() for part in parts if part.strip()]


def _extract_notice_metadata(page_content: str) -> dict[str, str]:
    """공지 텍스트의 상단 메타데이터에서 제목, 날짜, URL을 추출한다."""
    from datetime import datetime

    title_match = re.search(r"제목:\s*(.+)", page_content)
    date_match = re.search(r"날짜:\s*(.+)", page_content)
    url_match = re.search(r"URL:\s*(.+)", page_content)

    raw_date = date_match.group(1).strip() if date_match else "알 수 없음"
    parsed_date = raw_date
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S"):
        try:
            parsed_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
            break
        except Exception:
            continue

    return {
        "title": title_match.group(1).strip() if title_match else "알 수 없음",
        "date": parsed_date,
        "url": url_match.group(1).strip() if url_match else "",
    }


def _extract_menu_metadata(page_content: str) -> dict[str, str]:
    """식단 텍스트의 상단 메타데이터에서 기숙사, 날짜, URL을 추출한다."""
    dorm_match = re.search(r"기숙사:\s*(.+)", page_content)
    date_match = re.search(r"날짜:\s*(.+)", page_content)
    url_match = re.search(r"URL:\s*(.+)", page_content)

    raw_date = date_match.group(1).strip() if date_match else ""
    parsed_date = raw_date
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            parsed_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
            break
        except Exception:
            continue

    return {
        "dorm": dorm_match.group(1).strip() if dorm_match else "기숙사",
        "date": parsed_date,
        "url": url_match.group(1).strip() if url_match else "",
    }


def build_retriever():
    """data/raw/notices와 data/raw/dorm_menu의 .txt 파일들로 Chroma 벡터스토어를 만들고
    retriever를 반환한다.

    각 문서의 메타데이터를 chunk 앞에 추가해 검색 결과에 출처 정보를 담는다.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = []

    # 공지사항
    notice_loader = DirectoryLoader(
        "data/raw/notices",
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    for raw_doc in notice_loader.load():
        source_name = _source_name_from_path(raw_doc.metadata.get("source", ""))
        for notice_text in _split_into_notices(raw_doc.page_content):
            meta = _extract_notice_metadata(notice_text)
            meta["source"] = source_name
            header = (
                f"[공지사항]\n"
                f"제목: {meta['title']}\n"
                f"날짜: {meta['date']}\n"
                f"URL: {meta['url']}\n\n"
            )
            notice_doc = Document(page_content=notice_text, metadata=meta)
            for chunk in splitter.split_documents([notice_doc]):
                chunk.page_content = header + chunk.page_content
                split_docs.append(chunk)

    # 기숙사 식단
    menu_loader = DirectoryLoader(
        "data/raw/dorm_menu",
        glob="*/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    for raw_doc in menu_loader.load():
        meta = _extract_menu_metadata(raw_doc.page_content)
        meta["source"] = "dorm_menu"
        header = (
            f"[기숙사 식단]\n"
            f"기숙사: {meta['dorm']}\n"
            f"날짜: {meta['date']}\n"
            f"URL: {meta['url']}\n\n"
        )
        menu_doc = Document(page_content=raw_doc.page_content, metadata=meta)
        for chunk in splitter.split_documents([menu_doc]):
            chunk.page_content = header + chunk.page_content
            split_docs.append(chunk)

    vectorstore = Chroma.from_documents(
        documents=split_docs,
        embedding=OpenAIEmbeddings(),
        persist_directory="./chroma_db",
    )

    return vectorstore.as_retriever(search_kwargs={"k": 100})


@lru_cache(maxsize=1)
def get_retriever():
    """처음 사용할 때만 Chroma 벡터스토어를 구축한다."""
    return build_retriever()


class _LazyRetriever:
    """모듈 수준 retriever 참조를 유지하면서 지연 초기화를 수행하는 래퍼."""

    __slots__ = ()

    def invoke(self, query: str):
        return get_retriever().invoke(query)


retriever = _LazyRetriever()


class AgentState(TypedDict):
    """LangGraph 상태 정의."""

    messages: Annotated[list, add_messages]
    sources: list[str]
    confidence: str
    valid_input: bool


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_with_tools = llm.bind_tools([search_notices])


understand_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 충북대학교 정보 안내 챗봇입니다.\n"
            "학교/기숙사/학과 공지사항이나 기숙사 식단에 대한 구체적인 질문은 반드시 search_notices 도구를 사용하세요. "
            "일반 대화면 바로 답변하세요.\n"
            "예시: '기숙사 생활관비 납부 언제까지야?', '전자정보대학 장학 공지 있어?', "
            "'기숙사 입퇴거 날짜 알려줘', '오늘 양성재 메뉴 뭐야?' → 모두 search_notices를 호출하세요.\n"
            "사용자가 '최근'이나 '최신'을 언급한 경우, search_notices의 query 인자에 해당 키워드를 반드시 포함하세요. "
            "또한 사용자가 공지 출처(기숙사/생활관, 전자정보, 소프트웨어/컴공/컴퓨터, 학교/학사/본교)를 언급한 경우, "
            "search_notices의 query 인자에 해당 출처 키워드를 반드시 포함하세요.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


def understand_node(state: AgentState) -> dict:
    """사용자 질문을 이해하고 적절한 도구 호출 또는 답변을 생성한다."""
    chain = understand_prompt | llm_with_tools
    response = chain.invoke({"messages": state["messages"]})

    # 공지 출처 키워드가 빠지지 않도록 search_notices query를 보정한다.
    if isinstance(response, AIMessage) and response.tool_calls:
        last_human = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                last_human = msg.content
                break
        if last_human:
            is_meal = _is_meal_query(last_human)
            sources = _detect_sources(last_human, include_menu=is_meal)
            if sources:
                keyword = _source_injection_keyword(sources[0])
                for tool_call in response.tool_calls:
                    if tool_call.get("name") == "search_notices":
                        query = tool_call.get("args", {}).get("query", "")
                        if keyword not in query:
                            tool_call["args"]["query"] = f"{query} {keyword}".strip()

    return {"messages": [response]}


TOOLS_BY_NAME = {tool.name: tool for tool in [search_notices]}


def call_tool_node(state: AgentState) -> dict:
    """마지막 AIMessage의 tool_calls를 실행하고 결과를 반환한다."""
    last_message = state["messages"][-1]
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool = TOOLS_BY_NAME[tool_call["name"]]
        result = tool.invoke(tool_call["args"])
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )
    return {"messages": tool_messages}


def _extract_urls_from_messages(messages: list) -> list[str]:
    """ToolMessage나 HumanMessage에서 참고 URL 목록을 추출한다."""
    urls = []
    url_pattern = re.compile(r"https?://[^\s\]\)>\"]+")
    for msg in messages:
        if isinstance(msg, (AIMessage, ToolMessage, HumanMessage)):
            content = str(msg.content)
            # search_notices 결과에서 "URL: ..." 형태를 우선 추출
            for line in content.splitlines():
                if line.strip().startswith("URL:"):
                    url = line.split("URL:", 1)[1].strip()
                    if url and url not in urls:
                        urls.append(url)
            # 일반 URL도 추가
            for match in url_pattern.findall(content):
                if match not in urls:
                    urls.append(match)
    return urls


def _resolve_confidence(answer: str, sources: list[str]) -> str:
    """답변 내용과 출처 존재 여부에 따라 confidence를 결정한다."""
    if not sources:
        return "low"
    if any(phrase in answer for phrase in ("확인할 수 없습니다", "학교 홈페이지를 직접 확인")):
        return "medium"
    return "high"


def generate_node(state: AgentState) -> dict:
    """대화 기록과 도구 결과를 바탕으로 최종 답변을 생성한다."""
    parser = PydanticOutputParser(pydantic_object=FinalAnswer)
    messages = state["messages"]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 충북대학교 정보 안내 챗봇입니다. "
                "대화 기록과 검색된 정보를 바탕으로 사용자 질문에 대한 최종 답변을 생성하세요.\n"
                "검색된 공지나 식단 정보 중에서 사용자 질문과 직접 관련된 내용을 찾아 답변하세요. "
                "관련 정보가 명확하지 않더라도, 검색된 결과에서 가장 근접한 내용을 인용하여 답변을 구성하세요.\n"
                "검색된 공지나 식단 정보에 없는 내용은 절대 지어내지 마세요.\n"
                "정보가 부족하면 '해당 정보는 확인할 수 없습니다' 또는 '학교 홈페이지를 직접 확인해 주세요'라고 답변하세요.\n"
                "답변에 참고한 공지/식단의 제목(또는 기숙사), 날짜, URL을 포함하세요. "
                "검색 결과 중 날짜가 가장 최근인 문서를 우선적으로 참고하세요. "
                "sources 필드에는 참고한 문서의 URL을 정확히 채워넣으세요.\n"
                "{format_instructions}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | llm
    response = chain.invoke({"messages": messages})

    content = response.content if isinstance(response, AIMessage) else str(response)
    try:
        parsed = parser.parse(content)
    except Exception:
        parsed = FinalAnswer(answer=content, sources=[], confidence="low")

    # LLM이 sources를 비워둔 경우, 검색 결과에서 URL을 복원한다.
    if not parsed.sources:
        parsed.sources = _extract_urls_from_messages(messages)

    parsed.confidence = _resolve_confidence(parsed.answer, parsed.sources)

    return {
        "messages": [AIMessage(content=parsed.answer)],
        "sources": parsed.sources,
        "confidence": parsed.confidence,
    }


def route_after_understand(state: AgentState) -> str:
    """understand_node 이후 도구 호출 여부에 따라 분기한다."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "call_tool_node"
    return "generate_node"


def validate_input(user_input: str) -> bool:
    """사용자 입력이 비어 있지 않고 1000자 이하인지 검증한다."""
    if not isinstance(user_input, str):
        return False
    if not user_input.strip():
        return False
    return len(user_input) <= 1000


def log_middleware(state: AgentState) -> None:
    """최신 HumanMessage 내용과 현재 메시지 개수를 로깅한다."""
    messages = state.get("messages", [])
    last_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break
    logger.info("Latest human message: %s", last_human)
    logger.info("Current message count: %d", len(messages))


def middleware_node(state: AgentState) -> AgentState:
    """입력을 검증하고 로깅하는 미들웨어 노드."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_human = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_human = msg.content
            break

    if last_human is None:
        return {}

    if not validate_input(last_human):
        return {
            "messages": [
                AIMessage(content="입력이 너무 짧거나 길어서 처리할 수 없습니다.")
            ],
            "valid_input": False,
        }

    log_middleware(state)
    return {"valid_input": True}


def route_after_middleware(state: AgentState) -> str:
    """middleware_node 이후 입력 검증 결과에 따라 분기한다."""
    if state.get("valid_input") is False:
        return END
    return "understand_node"


builder = StateGraph(AgentState)
builder.add_node("middleware", middleware_node)
builder.add_node("understand_node", understand_node)
builder.add_node("call_tool_node", call_tool_node)
builder.add_node("generate_node", generate_node)
builder.add_edge(START, "middleware")
builder.add_conditional_edges(
    "middleware",
    route_after_middleware,
    {"understand_node": "understand_node", END: END},
)
builder.add_conditional_edges(
    "understand_node",
    route_after_understand,
    {"call_tool_node": "call_tool_node", "generate_node": "generate_node"},
)
builder.add_edge("call_tool_node", "generate_node")
builder.add_edge("generate_node", END)
graph = builder.compile(checkpointer=MemorySaver())


def run_agent(user_input: str, thread_id: str = "web") -> dict[str, str | list[str]]:
    """순수 함수 형태의 에이전트 실행 진입점.

    HTML UI나 API 서버에서 호출할 때 사용한다.
    주어진 user_input을 graph에 전달하고 답변과 참고 출처를 반환한다.
    """
    if not validate_input(user_input):
        return {"answer": "입력이 너무 짧거나 길어서 처리할 수 없습니다.", "sources": [], "confidence": "low"}

    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke(
        {
            "messages": [("human", user_input)],
            "sources": [],
            "confidence": "medium",
            "valid_input": True,
        },
        config,
    )
    last_message = state["messages"][-1]
    answer = (
        last_message.content if isinstance(last_message, AIMessage) else str(last_message)
    )
    sources = state.get("sources", [])
    confidence = state.get("confidence", "medium")

    greeting_keywords = ["안녕", "반가워", "hello", "hi", "처음", "누구"]
    is_greeting = any(kw in user_input.lower() for kw in greeting_keywords)

    if (confidence == "low" or not sources) and not is_greeting:
        answer += "\n\n[참고] 답변 근거가 충분하지 않을 수 있습니다. 정확한 정보는 학교 홈페이지를 확인해 주세요."

    return {"answer": answer, "sources": sources, "confidence": confidence}


def run_cli() -> None:
    """터미널에서 대화형으로 에이전트와 대화할 수 있는 CLI 루프."""
    if not sys.stdin.isatty():
        try:
            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("충북대학교 정보 안내 챗봇 CBNU Agent에 오신 것을 환영합니다!")
    print("종료하려면 'exit', 'quit' 또는 '종료'를 입력하세요.\n")

    config = {"configurable": {"thread_id": "cli"}}
    while True:
        try:
            user_input = input("사용자: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if user_input.lower() in {"exit", "quit", "종료"}:
            print("종료합니다.")
            break

        if not user_input:
            continue

        state = graph.invoke(
            {
                "messages": [("human", user_input)],
                "sources": [],
                "confidence": "medium",
                "valid_input": True,
            },
            config,
        )
        last_message = state["messages"][-1]
        print(f"에이전트: {last_message.content}\n")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "web"


app = FastAPI(title="CBNU Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return FileResponse("index.html")


@app.post("/api/chat")
def chat(req: ChatRequest):
    result = run_agent(req.message, req.thread_id)
    return JSONResponse(
        {"answer": result["answer"], "sources": result["sources"], "confidence": result["confidence"]}
    )


if __name__ == "__main__":
    run_cli()
