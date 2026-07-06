"""크롤링 공통 유틸리티"""

import os
import re
import requests
from bs4 import BeautifulSoup


def fetch_html(url: str) -> BeautifulSoup:
    """URL에서 HTML을 받아 BeautifulSoup 객체로 반환한다."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def clean_text(text: str) -> str:
    """연속된 공백과 개행을 정리한다."""
    return re.sub(r"\s+", " ", text).strip()


def save_text(text: str, path: str) -> None:
    """텍스트를 UTF-8 파일로 저장한다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def absolutize_href(href: str, base_url: str) -> str:
    """상대 경로를 절대 URL로 변환한다."""
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        # base_url이 https://domain.com/path 형태일 수 있으므로 루트 기준
        from urllib.parse import urljoin

        return urljoin(base_url, href)
    # 같은 경로의 상대 링크
    from urllib.parse import urljoin

    return urljoin(base_url, href)
