"""기숙사 식단 크롤러

- 개성재: type=1
- 양성재: type=2
- 양진재: type=3
"""

import re
from datetime import date, datetime, timedelta, timezone

from src.crawlers.utils import fetch_html, clean_text, save_text

DORM_MENU_URL = "https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20041&type={type}"
DORM_NAME_MAP = {
    "1": "개성재",
    "2": "양성재",
    "3": "양진재",
}


def _resolve_year(month: int, day: int, reference_date: date) -> int:
    """월/일만 제공될 때 reference_date에 가장 가까운 연도를 선택한다."""
    best_year = reference_date.year
    best_diff = None
    for year in (reference_date.year - 1, reference_date.year, reference_date.year + 1):
        try:
            diff = abs((date(year, month, day) - reference_date).days)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_year = year
        except ValueError:
            continue
    return best_year


def _parse_menu_date(day_text: str, reference_date: date | None = None) -> date | None:
    """식단 테이블의 첫 셀 텍스트에서 날짜를 추출한다."""
    if reference_date is None:
        reference_date = datetime.now(timezone(timedelta(hours=9))).date()

    text = clean_text(day_text)

    # YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # M.D, MM.DD
    match = re.search(r"(\d{1,2})[/.](\d{1,2})", text)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = _resolve_year(month, day, reference_date)
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def fetch_dorm_menu(dorm_type: str = "1") -> list[dict]:
    """기숙사 식단 페이지에서 주간 식단을 날짜별로 추출한다."""
    url = DORM_MENU_URL.format(type=dorm_type)
    soup = fetch_html(url)
    dorm_name = DORM_NAME_MAP.get(dorm_type, "기숙사")
    reference_date = datetime.now(timezone(timedelta(hours=9))).date()

    table = soup.find("table", class_="m_table_c")
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

    menus = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < len(headers):
            continue
        row_texts = [cell.get_text(separator=" ", strip=True) for cell in cells]
        menu_date = _parse_menu_date(row_texts[0], reference_date)
        if menu_date is None:
            continue

        lines = [
            f"기숙사: {dorm_name}",
            f"날짜: {menu_date.isoformat()}",
            f"URL: {url}",
        ]
        for header, text in zip(headers[1:], row_texts[1:]):
            lines.append(f"[{header}]: {clean_text(text)}")

        menus.append(
            {
                "date": menu_date.isoformat(),
                "dorm": dorm_name,
                "url": url,
                "content": "\n".join(lines),
            }
        )

    return menus


def crawl_all_dorm_menus(save_dir: str = "data/raw/dorm_menu") -> None:
    """3개 기숙사 식단을 모두 크롤링해서 날짜별 파일로 저장한다."""
    for dorm_type, dorm_name in DORM_NAME_MAP.items():
        menus = fetch_dorm_menu(dorm_type)
        for menu in menus:
            path = f"{save_dir}/{dorm_name}/{menu['date']}.txt"
            save_text(menu["content"], path)
        print(f"Saved {dorm_name} menu ({len(menus)} days)")


if __name__ == "__main__":
    crawl_all_dorm_menus()
    # 테스트 출력
    print("\n--- 양성재 오늘 메뉴 테스트 ---")
    today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    for menu in fetch_dorm_menu("2"):
        if menu["date"] == today:
            print(menu["content"])
            break
