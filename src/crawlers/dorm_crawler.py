"""기숙사 식단 크롤러

- 개성재: type=1
- 양성재: type=2
- 양진재: type=3
"""

from src.crawlers.utils import fetch_html, clean_text, save_text

DORM_MENU_URL = "https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20041&type={type}"
DORM_NAME_MAP = {
    "1": "개성재",
    "2": "양성재",
    "3": "양진재",
}


def fetch_dorm_menu(dorm_type: str = "1") -> str:
    """기숙사 식단 페이지에서 오늘의 식단 텍스트를 추출한다."""
    url = DORM_MENU_URL.format(type=dorm_type)
    soup = fetch_html(url)

    table = soup.find("table", class_="m_table_c")
    if not table:
        return "식단 정보를 찾을 수 없습니다."

    rows = table.find_all("tr")
    if len(rows) < 2:
        return "식단 정보를 찾을 수 없습니다."

    # 첫 번째 행은 헤더(구분, 아침, 점심, 저녁)
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

    lines = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < len(headers):
            continue
        row_texts = [cell.get_text(separator=" ", strip=True) for cell in cells]
        # 첫 번째 셀: 날짜/요일
        day = clean_text(row_texts[0])
        # 오늘 날짜가 포함된 행만 추출 (오늘 하루)
        # 페이지가 오늘 날짜를 포함하므로, 첫 번째 데이터 행이 오늘
        if not lines:
            # 첫 데이터 행 = 오늘
            lines.append(f"[{DORM_NAME_MAP.get(dorm_type, '기숙사')} 오늘의 식단]")
            for h, t in zip(headers[1:], row_texts[1:]):
                lines.append(f"- {h}: {clean_text(t)}")
            break

    return "\n".join(lines) if lines else "식단 정보를 찾을 수 없습니다."


def crawl_all_dorm_menus(save_dir: str = "data/raw/dorm_menu") -> None:
    """3개 기숙사 식단을 모두 크롤링해서 저장한다."""
    for dorm_type, dorm_name in DORM_NAME_MAP.items():
        menu_text = fetch_dorm_menu(dorm_type)
        path = f"{save_dir}/{dorm_name}.txt"
        save_text(menu_text, path)
        print(f"Saved {dorm_name} menu to {path}")


if __name__ == "__main__":
    crawl_all_dorm_menus()
    # 테스트 출력
    print("\n--- 개성재 테스트 ---")
    print(fetch_dorm_menu("1"))
