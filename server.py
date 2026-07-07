"""CBNU Agent RAG 서버 모듈.

공지사항 텍스트 파일을 로드하고 벡터 스토어를 구축하여
유사도 기반 문서 검색(retriever)을 제공합니다.
"""

import os
from datetime import date

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def fetch_html(url: str) -> BeautifulSoup:
    """주어진 URL의 HTML을 요청하고 BeautifulSoup 객체를 반환한다."""
    headers = {"User-Agent": "Mozilla/5.0 (CBNU-Agent/1.0)"}
    response = requests.get(url, headers=headers, timeout=30)
    response.encoding = "utf-8"
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

    # 오늘 날짜를 찾지 못하면 전체 테이블 텍스트를 반환한다.
    return f"[{dorm_name} 식단]\n{table.get_text(separator='\n', strip=True)}"


@tool
def search_notices(query: str) -> str:
    """공지사항 벡터 스토어에서 query와 관련된 내용을 검색한다.

    Args:
        query: 검색할 키워드나 문장.

    Returns:
        검색된 공지사항 내용을 두 줄 개행으로 연결한 문자열.
    """
    docs = retriever.invoke(query)
    return "\n\n".join(doc.page_content for doc in docs)


def build_retriever():
    """data/raw/notices의 .txt 파일들로 Chroma 벡터스토어를 만들고 retriever를 반환한다."""
    loader = DirectoryLoader(
        "data/raw/notices",
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    split_docs = splitter.split_documents(documents)

    vectorstore = Chroma.from_documents(
        documents=split_docs,
        embedding=OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
        persist_directory="./chroma_db",
    )

    return vectorstore.as_retriever(search_kwargs={"k": 3})


retriever = build_retriever()
