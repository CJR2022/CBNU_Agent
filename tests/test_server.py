"""server.py 모듈 단위 테스트"""

import math
import os
from unittest.mock import patch

import pytest


class _FakeEmbeddings:
    """OpenAI API 호출 없이 의미 있는 검색 결과를 얻기 위한 가짜 임베딩.

    텍스트에 포함된 문자를 1536차원 공간에 희소 벡터로 매핑합니다.
    쿼리와 공통 문자가 많을수록 거리가 가까워지므로,
    '등록금 납부 기간' 같은 쿼리로 '등록금'이 포함된 문서를 검색할 수 있습니다.
    """

    _DIMENSION = 1536

    def __init__(self, *args, **kwargs):
        pass

    def _embed(self, text):
        vector = [0.0] * self._DIMENSION
        for char in text:
            vector[ord(char) % self._DIMENSION] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


@pytest.fixture(scope="module")
def server_mod():
    """OpenAIEmbeddings를 모킹한 상태에서 server 모듈을 임포트한다."""
    with patch("langchain_openai.OpenAIEmbeddings", _FakeEmbeddings):
        import server

        yield server


def test_build_retriever_is_callable(server_mod):
    """build_retriever를 임포트할 수 있어야 한다."""
    assert callable(server_mod.build_retriever)


def test_module_level_retriever_exists_with_invoke(server_mod):
    """모듈 수준 retriever가 존재하고 invoke 메서드를 가져야 한다."""
    assert server_mod.retriever is not None
    assert hasattr(server_mod.retriever, "invoke")
    assert callable(server_mod.retriever.invoke)


@pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY") == "",
    reason="No OpenAI API key available",
)
def test_retriever_returns_relevant_documents(server_mod):
    """실제 API 키가 있을 때 등록금 관련 문서를 검색한다."""
    docs = server_mod.retriever.invoke("등록금 납부 기간")
    assert len(docs) == 3
    assert any("등록금" in doc.page_content for doc in docs)
