"""CBNU Agent RAG 서버 모듈.

LangGraph 기반 에이전트를 구성하며, middleware 노드, 도구 노드, 그리고
대화형 CLI와 `run_agent()` API 진입점을 제공합니다.

주요 구성 요소:
- LangGraph `StateGraph`: middleware → understand → tool/generate 워크플로우
- `middleware_node`: 입력 검증 및 로깅
- `get_dorm_menu`, `search_notices`: 기숙사 식단 및 공지사항 검색 도구
- `run_cli()`: 터미널 대화형 CLI
- `run_agent()`: HTML UI 및 API 서버에서 호출하는 순수 함수형 진입점
"""

import logging
import re
import sys
from datetime import date
from typing import Annotated

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

    answer: str = Field(description="사용자 질문에 대한 최종 답변. 검색된 정볼만 사용하고, 정보가 없으면 '해당 정보는 확인할 수 없습니다'라고 답변하세요.")
    sources: list[str] = Field(description="참고한 공지 URL 목록")
    confidence: str = Field(description="답변 확신도: high, medium, low 중 하나. 근거가 충분하면 high, 부족하면 low")


def fetch_html(url: str) -> BeautifulSoup:
    """주어진 URL의 HTML을 요청하고 BeautifulSoup 객체를 반환한다."""
    headers = {"User-Agent": "Mozilla/5.0 (CBNU-Agent/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.encoding = "utf-8"
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


_DORM_TYPE_MAP = {
    "개성재": "1",
    "양성재": "2",
    "양진재": "3",
}


@tool
def get_dorm_menu(dorm_name: str = "개성재") -> str:
    """충북대학교 기숙사 식단을 조회한다.

    Args:
        dorm_name: 기숙사 이름 (개성재, 양성재, 양진재).

    Returns:
        오늘 날짜의 식단을 문자열로 반환한다.
    """
    type_code = _DORM_TYPE_MAP.get(dorm_name, "1")
    url = f"https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20041&type={type_code}"
    soup = fetch_html(url)

    table = soup.select_one("table.m_table_c")
    if table is None:
        return f"{dorm_name} 식단 정보를 찾을 수 없습니다."

    today = date.today()
    today_patterns = [
        f"{today.month}월 {today.day}일",
        f"{today.month:02d}.{today.day:02d}",
        f"{today.month}/{today.day}",
        f"{today.month}.{today.day}",
    ]

    rows = table.find_all("tr")
    for row in rows:
        row_text = row.get_text(separator=" ", strip=True)
        if any(pattern in row_text for pattern in today_patterns):
            return f"[{dorm_name} 오늘의 식단]\n{row_text}"

    # 오늘 날짜를 찾지 못하면 안내 메시지를 반환한다.
    return f"[{dorm_name}] 오늘의 식단 정보를 찾을 수 없습니다. 기숙사 식단 페이지에서 확인해 주세요. ({url})"


@tool
def search_notices(query: str) -> str:
    """학교/전자정보/소프트웨어/기숙사 공지사항 벡터 스토어에서 query와 관련된 내용을 검색한다.

    Args:
        query: 검색할 키워드나 문장.

    Returns:
        검색된 공지사항 내용을 두 줄 개행으로 연결한 문자열.
    """
    docs = retriever.invoke(query)
    if not docs:
        return "관련 공지를 찾을 수 없습니다."

    recent_keywords = ["최근", "최신", "최근 공지", "최신 공지"]
    if any(keyword in query for keyword in recent_keywords):

        def _sort_key(doc):
            date_str = doc.metadata.get("date", "")
            try:
                return (True, date.fromisoformat(date_str), date_str)
            except Exception:
                return (False, date.min, date_str)

        # 최신 공지를 보장하기 위해 원본 파일에서 최근 공지도 함께 포함한다.
        try:
            loader = DirectoryLoader(
                "data/raw/notices",
                glob="*.txt",
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8"},
            )
            raw_documents = loader.load()
        except Exception:
            raw_documents = []

        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=150)
        latest_docs = []
        for raw_doc in raw_documents:
            for notice_text in _split_into_notices(raw_doc.page_content):
                meta = _extract_notice_metadata(notice_text)
                header = (
                    f"[출처]\n"
                    f"제목: {meta['title']}\n"
                    f"날짜: {meta['date']}\n"
                    f"URL: {meta['url']}\n\n"
                )
                notice_doc = Document(
                    page_content=notice_text,
                    metadata={"title": meta["title"], "date": meta["date"], "url": meta["url"]},
                )
                for chunk in splitter.split_documents([notice_doc]):
                    chunk.page_content = header + chunk.page_content
                    latest_docs.append(chunk)

        seen_urls = {doc.metadata.get("url") for doc in docs}
        for doc in sorted(latest_docs, key=_sort_key, reverse=True)[:10]:
            if doc.metadata.get("url") not in seen_urls:
                docs.append(doc)
                seen_urls.add(doc.metadata.get("url"))

        docs = sorted(docs, key=_sort_key, reverse=True)[:5]

    return "\n\n".join(doc.page_content for doc in docs)


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


def build_retriever():
    """data/raw/notices의 .txt 파일들로 Chroma 벡터스토어를 만들고 retriever를 반환한다.

    각 공지의 메타데이터(제목, 날짜, URL)를 해당 공지에서 나뉜 모든 chunk 앞에 추가한다.
    """
    loader = DirectoryLoader(
        "data/raw/notices",
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    raw_documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=150)

    split_docs = []
    for raw_doc in raw_documents:
        for notice_text in _split_into_notices(raw_doc.page_content):
            meta = _extract_notice_metadata(notice_text)
            header = (
                f"[출처]\n"
                f"제목: {meta['title']}\n"
                f"날짜: {meta['date']}\n"
                f"URL: {meta['url']}\n\n"
            )
            notice_doc = Document(
                page_content=notice_text, metadata={"title": meta["title"], "date": meta["date"], "url": meta["url"]}
            )
            for chunk in splitter.split_documents([notice_doc]):
                chunk.page_content = header + chunk.page_content
                split_docs.append(chunk)

    vectorstore = Chroma.from_documents(
        documents=split_docs,
        embedding=OpenAIEmbeddings(),
        persist_directory="./chroma_db",
    )

    return vectorstore.as_retriever(search_kwargs={"k": 5})


retriever = build_retriever()


class AgentState(TypedDict):
    """LangGraph 상태 정의."""

    messages: Annotated[list, add_messages]
    sources: list[str]
    confidence: str


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_with_tools = llm.bind_tools([get_dorm_menu, search_notices])


understand_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 충북대학교 정보 안내 챗봇입니다. 기숙사 식단 질문이면 get_dorm_menu 도구를, "
            "공지사항 관련 질문이면 search_notices 도구를, 일반 대화면 바로 답변하세요. "
            "사용자가 '최근'이나 '최신'을 언급한 경우, search_notices의 query 인자에 해당 키워드를 반드시 포함하세요.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)


def understand_node(state: AgentState) -> dict:
    """사용자 질문을 이해하고 적절한 도구 호출 또는 답변을 생성한다."""
    chain = understand_prompt | llm_with_tools
    response = chain.invoke({"messages": state["messages"]})
    return {"messages": [response]}


TOOLS_BY_NAME = {tool.name: tool for tool in [get_dorm_menu, search_notices]}


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
                "검색된 공지나 조회된 식단 정보에 없는 내용은 절대 지어내지 마세요.\n"
                "정보가 부족하면 '해당 정보는 확인할 수 없습니다' 또는 '학교 홈페이지를 직접 확인해 주세요'라고 답변하세요.\n"
                "답변에 참고한 공지의 제목, 날짜, URL을 포함하세요. "
                "검색 결과 중 날짜가 가장 최근인 공지를 우선적으로 참고하세요. "
                "sources 필드에는 참고한 공지의 URL을 채워넣으세요.\n"
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
            ]
        }

    log_middleware(state)
    return {}


def route_after_middleware(state: AgentState) -> str:
    """middleware_node 이후 입력 검증 결과에 따라 분기한다."""
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        if "입력이 너무 짧거나 길어서 처리할 수 없습니다." in messages[-1].content:
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
    state = graph.invoke({"messages": [("human", user_input)], "sources": [], "confidence": "medium"}, config)
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

        state = graph.invoke({"messages": [("human", user_input)]}, config)
        last_message = state["messages"][-1]
        print(f"에이전트: {last_message.content}\n")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "web"


app = FastAPI(title="CBNU Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
