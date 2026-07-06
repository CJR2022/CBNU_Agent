"""공지사항 크롤러

수집 대상:
- 충북대학교 학사/장학 공지
- 전자정볼대학 공지
- 소프트웨어학부 학부공지
- 기숙사 공지
"""

from src.crawlers.utils import fetch_html, clean_text, save_text, absolutize_href

# (이름, 목록 URL, 베이스 URL)
NOTICE_SOURCES = [
    (
        "main",
        "https://www.chungbuk.ac.kr/www/selectBbsNttList.do?bbsNo=8&key=815&searchCtgry=학사/장학",
        "https://www.chungbuk.ac.kr/www/",
    ),
    (
        "ece",
        "https://ece.cbnu.ac.kr/ece0602",
        "https://ece.cbnu.ac.kr/",
    ),
    (
        "sw",
        "https://software.cbnu.ac.kr/sub0401",
        "https://software.cbnu.ac.kr/",
    ),
    (
        "dorm",
        "https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20039",
        "https://dorm.chungbuk.ac.kr/home/",
    ),
]


def extract_notice_links(list_url: str, base_url: str) -> list[dict]:
    """공지사항 목록 페이지에서 제목과 본문 링크를 추출한다."""
    soup = fetch_html(list_url)
    links = []

    # 각 사이트의 테이블 선택자 우선순위
    table = (
        soup.find("table", class_="p-table")
        or soup.find("table", class_="bd_lst")
        or soup.find("table", class_="board")
        or soup.find("table")
    )
    if not table:
        return links

    for row in table.find_all("tr")[1:]:  # 헤더 제외
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        # 제목이 담긴 셀 찾기
        a_tag = None
        for cell in cells:
            a = cell.find("a", href=True)
            if a:
                a_tag = a
                break

        if not a_tag:
            continue

        title = clean_text(a_tag.get_text(strip=True))
        href = absolutize_href(a_tag["href"], base_url)

        # 광고/불필요 링크 필터
        if not title or href.startswith("#") or "javascript" in href.lower():
            continue

        links.append({"title": title, "url": href})

    return links


def extract_notice_detail(detail_url: str) -> dict:
    """공지사항 본문 페이지에서 제목, 작성일, 본문, 첨부파일을 추출한다."""
    soup = fetch_html(detail_url)

    title = ""
    date = ""
    content = ""
    attachments = []

    # 제목
    title_tag = soup.find("h2") or soup.find(class_=lambda x: x and "title" in x.lower())
    if title_tag:
        title = clean_text(title_tag.get_text())

    # 작성일
    for text in soup.stripped_strings:
        if any(k in text for k in ["작성일", "등록일", "Date"]):
            date = clean_text(text.replace("작성일", "").replace("등록일", "").replace("Date", ""))
            break
        # yyyy.mm.dd or yyyy/mm/dd or yyyy-mm-dd 형태
        import re

        if re.search(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text):
            date = clean_text(text)
            break

    # 본문 영역
    content_selectors = [
        ("div", {"class": "content"}),
        ("div", {"class": "cont"}),
        ("div", {"class": "view_cont"}),
        ("div", {"class": "bbs_content"}),
        ("article", {}),
    ]
    for tag, attrs in content_selectors:
        el = soup.find(tag, attrs)
        if el:
            content = clean_text(el.get_text(separator="\n", strip=True))
            break

    # 첨부파일 링크
    for a in soup.find_all("a", href=True):
        href = absolutize_href(a["href"], detail_url)
        if any(href.lower().endswith(ext) for ext in [".pdf", ".hwp", ".doc", ".docx", ".xls", ".xlsx"]):
            attachments.append(f"{clean_text(a.get_text(strip=True))}: {href}")

    return {
        "title": title,
        "date": date,
        "content": content,
        "attachments": attachments,
        "url": detail_url,
    }


def format_notice(notice: dict) -> str:
    """공지사항 딕셔너리를 저장용 텍스트로 변환한다."""
    lines = [
        f"제목: {notice['title']}",
        f"날짜: {notice['date']}",
        f"URL: {notice['url']}",
    ]
    if notice["attachments"]:
        lines.append("첨부파일:")
        for att in notice["attachments"]:
            lines.append(f"  - {att}")
    lines.append("본문:")
    lines.append(notice["content"])
    lines.append("\n" + "=" * 50 + "\n")
    return "\n".join(lines)


def crawl_notices(source_name: str, list_url: str, base_url: str) -> str:
    """하나의 공지사항 소스를 크롤링해서 통합 텍스트로 반환한다."""
    print(f"Crawling {source_name} ...")
    links = extract_notice_links(list_url, base_url)
    print(f"  found {len(links)} notices")

    parts = [f"# {source_name} 공지사항\n"]
    for item in links[:20]:  # 첫 페이지, 최대 20건
        try:
            detail = extract_notice_detail(item["url"])
            detail["title"] = detail["title"] or item["title"]
            parts.append(format_notice(detail))
        except Exception as e:
            print(f"  failed to fetch {item['url']}: {e}")
    return "\n".join(parts)


def crawl_all_notices(save_dir: str = "data/raw/notices") -> None:
    """4개 공지사항 소스를 모두 크롤링해서 저장한다."""
    for name, list_url, base_url in NOTICE_SOURCES:
        text = crawl_notices(name, list_url, base_url)
        path = f"{save_dir}/{name}_notice.txt"
        save_text(text, path)
        print(f"Saved {name} notices to {path}\n")


if __name__ == "__main__":
    crawl_all_notices()
