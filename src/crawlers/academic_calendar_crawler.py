"""학사일정 크롤러

충북대학교 학사일정 페이지에서 연도별 학사일정을 수집한다.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.crawlers.utils import fetch_html, clean_text, save_text

logger = logging.getLogger(__name__)

ACADEMIC_CALENDAR_URL = (
    "https://www.cbnu.ac.kr/www/selectWebSchdulList.do?key=455&schdulSeNo=1"
)


def _parse_date_range(date_text: str) -> tuple[str, str]:
    """'03.03.(화)' 또는 '02.02.(월) ~ 02.06.(금)' 형태를 (시작일, 종료일)로 변환한다.

    연도는 페이지의 학사일정 연도를 사용한다. 형식이 맞지 않으면 원본을 그대로 반환한다.
    """
    date_text = clean_text(date_text)
    if not date_text:
        return "", ""

    # 'MM.DD.(요일)' 또는 'MM.DD.(요일) ~ MM.DD.(요일)' 패턴
    parts = re.split(r"\s*~\s*", date_text)
    parsed = []
    for part in parts:
        # 현재는 연도를 직접 알 수 없으므로 원본 텍스트를 반환한다.
        # parse_year 파라미터가 주어지면 YYYY-MM-DD로 변환할 수 있다.
        parsed.append(part)
    if len(parsed) == 1:
        return parsed[0], ""
    return parsed[0], parsed[1]


def _infer_year(soup: BeautifulSoup) -> int:
    """페이지에서 학사일정 연도를 추론한다.

    본문 학사일정 제목의 'YYYY학년도' 패턴을 우선적으로 찾고,
    없으면 페이지 전체에서 'YYYY 학년도' 또는 'YYYY학년도' 형태를 찾는다.
    """
    # 1순위: 본문 일정 제목에서 '2026학년도' 형태 추출
    table = soup.find("table")
    if table:
        for text in table.stripped_strings:
            match = re.search(r"(20\d{2})\s*학년도", text)
            if match:
                return int(match.group(1))

    # 2순위: 페이지 전체에서 '2026 학년도' 또는 '2026학년도' 형태 추출
    for text in soup.stripped_strings:
        match = re.search(r"(20\d{2})\s*학년도", text)
        if match:
            return int(match.group(1))

    return datetime.now().year


def extract_academic_calendar(url: str = ACADEMIC_CALENDAR_URL) -> list[dict]:
    """학사일정 페이지에서 일정 목록을 추출한다.

    Returns:
        [
            {
                "month": "3월",
                "period": "03.03.(화)",
                "title": "1학기 개강",
                "url": "...",
            },
            ...
        ]
    """
    soup = fetch_html(url)
    year = _infer_year(soup)

    schedules = []
    table = soup.find("table")
    if not table:
        logger.warning("학사일정 테이블을 찾을 수 없습니다.")
        return schedules

    current_month = ""
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        first_text = clean_text(cells[0].get_text())

        # 헤더 행 스킵
        if first_text in ("월", "일(요일)", "학사내용"):
            continue

        # 월 행: ['1월', '', '']
        if "월" in first_text and len(first_text) <= 4:
            current_month = first_text
            continue

        # 데이터 행: ['기간', '내용'] 또는 ['기간', '', '내용']
        if len(cells) == 2:
            period = clean_text(cells[0].get_text())
            title = clean_text(cells[1].get_text())
        elif len(cells) >= 3:
            period = clean_text(cells[0].get_text())
            title = clean_text(cells[2].get_text())
        else:
            continue

        if not period or not title or "일(요일)" in period:
            continue

        schedules.append(
            {
                "year": year,
                "month": current_month,
                "period": period,
                "title": title,
                "url": url,
            }
        )

    return schedules


def format_academic_calendar(schedules: list[dict]) -> str:
    """학사일정 목록을 저장용 텍스트로 변환한다."""
    lines = ["# 학사일정\n"]
    for item in schedules:
        lines.extend(
            [
                f"제목: {item['title']}",
                f"기간: {item['period']}",
                f"URL: {item['url']}",
                "",
                "=" * 50,
                "",
            ]
        )
    return "\n".join(lines)


def crawl_academic_calendar(
    url: str = ACADEMIC_CALENDAR_URL,
    save_dir: str = "data/raw/academic_calendar",
) -> str:
    """학사일정을 크롤링하고 저장한다. 저장된 파일 경로를 반환한다."""
    schedules = extract_academic_calendar(url)
    text = format_academic_calendar(schedules)
    year = schedules[0]["year"] if schedules else datetime.now().year
    path = f"{save_dir}/{year}.txt"
    save_text(text, path)
    logger.info("학사일정 %d개를 %s에 저장했습니다.", len(schedules), path)
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawl_academic_calendar()
