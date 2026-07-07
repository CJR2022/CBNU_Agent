"""공지사항 크롤러

수집 대상:
- 충북대학교 학사/장학 공지
- 전자정볼대학 공지
- 소프트웨어학부 학부공지
- 기숙사 공지
"""

import re
from io import BytesIO

import requests
from pypdf import PdfReader

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


def extract_pdf_text(url: str) -> str:
    """PDF 파일 URL에서 텍스트를 추출한다."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return clean_text(text)
    except Exception as e:
        return f"[PDF 추출 실패: {e}]"


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


# 제목으로 사용하지 않을 일반적인 낸비게이션/메뉴 텍스트
_EXCLUDED_TITLES = {
    "전체",
    "공지사항",
    "알림마당",
    "상세보기",
    "주메뉴",
    "주메뉴닫기",
    "제목",
    "목록",
    "게시물삭제",
    "삭제 이유",
    "본인 삭제 - 문제해결",
    "본인 삭제 - 단순변심",
    "본인 삭제 - 추후 재작성 예정",
}


def _extract_title(soup, detail_url: str, fallback_title: str) -> str:
    """공지 본문 페이지에서 제목을 추출한다.

    사이트별 DOM 구조에 맞춰 우선적으로 추출하고, 실패하면 fallback_title을 반환한다.
    """
    # 1. 충북대 메인 홈페이지: <div class="subjectbox">가 실제 제목을 담고 있음
    if "chungbuk.ac.kr/www" in detail_url:
        el = soup.find("div", class_="subjectbox")
        if el:
            text = clean_text(el.get_text())
            if text and text not in _EXCLUDED_TITLES:
                return text

    # 2. 기숙사: 본문 영역 첫 줄에 "제목 - 게시글 상세보기" 형태로 들어 있음
    if "dorm.chungbuk.ac.kr" in detail_url:
        container = soup.find("div", class_="containerIn")
        if container:
            first_line = container.get_text(separator="\n", strip=True).splitlines()[0]
            if " - " in first_line:
                text = clean_text(first_line.split(" - ")[0])
                if text and text not in _EXCLUDED_TITLES:
                    return text

    # 3. 전자정볼대학/소프트웨어학부: <title> 태그가 "사이트명 - 제목" 형태
    if soup.title:
        title_text = clean_text(soup.title.get_text())
        if " - " in title_text:
            text = title_text.split(" - ")[-1].strip()
            if text and text not in _EXCLUDED_TITLES:
                return text

    # 4. 범용 폴백: h1/h2/h3/h4 중 의미 있는 텍스트
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = clean_text(tag.get_text())
        if text and text not in _EXCLUDED_TITLES:
            return text

    return fallback_title


def _extract_date(soup) -> str:
    """공지 본문 페이지에서 작성일을 추출한다."""
    # 작성일/등록일 키워드 우선
    for text in soup.stripped_strings:
        if any(k in text for k in ["작성일", "등록일", "Date"]):
            cleaned = re.sub(r".*작성일|.*등록일|.*Date", "", text)
            cleaned = clean_text(cleaned)
            if cleaned:
                return cleaned

    # 날짜 패턴 탐색
    for text in soup.stripped_strings:
        match = re.search(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", text)
        if match:
            return clean_text(text)

    return ""


def _clean_nav_text(text: str) -> str:
    """본문 끝에 붙은 낸비게이션/UI 텍스트를 제거한다."""
    nav_markers = [
        "다음글, 이전글 보기",
        "대학생활-공지사항 상세보기",
        "List of Articles",
        "Board Pagination",
    ]
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 낸비게이션 마커가 등장하면 그 뒤는 모두 버린다
        if any(stripped.startswith(marker) for marker in nav_markers):
            break
        if stripped in {
            "이전글",
            "다음글",
            "목록",
            "게시물삭제",
            "삭제 이유",
            "본인 삭제 - 문제해결",
            "본인 삭제 - 단순변심",
            "본인 삭제 - 추후 재작성 예정",
            "위로",
            "아래로",
            "댓글로 가기",
            "인쇄",
            "첨부",
            "Prev",
            "Next",
            "GO",
        }:
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_content(soup, detail_url: str) -> str:
    """공지 본문 페이지에서 본문 텍스트를 추출한다.

    사이트별로 본문 영역 선택자를 다르게 적용한 뒤, 낸비게이션 텍스트를 정제한다.
    """
    # 사이트별 본문 영역 우선 선택
    if "chungbuk.ac.kr/www" in detail_url:
        el = soup.find("div", class_="contenttext") or soup.find("div", class_="viewcontent")
    elif "ece.cbnu.ac.kr" in detail_url or "software.cbnu.ac.kr" in detail_url:
        el = soup.find("div", class_="rd_body")
    elif "dorm.chungbuk.ac.kr" in detail_url:
        el = soup.find("div", class_="containerIn")
    else:
        el = None

    # 평백: 일반적인 본문 선택자
    if not el:
        for tag, attrs in [
            ("div", {"class": "content"}),
            ("div", {"class": "cont"}),
            ("div", {"class": "containerIn"}),
            ("div", {"class": "board_insert"}),
            ("div", {"class": "view_cont"}),
            ("div", {"class": "bbs_content"}),
            ("article", {}),
        ]:
            el = soup.find(tag, attrs)
            if el:
                break

    if not el:
        return ""

    # 줄 단위 텍스트를 먼저 얻은 뒤 낸비게이션을 제거하고, 마지막에 공백을 정리한다.
    text = el.get_text(separator="\n", strip=True)

    # 기숙사 본문 영역 첫 줄 "제목 - 게시글 상세보기"는 제목 중복이므로 본문에서는 제거
    if "dorm.chungbuk.ac.kr" in detail_url:
        lines = text.splitlines()
        if lines and " - 게시글 상세보기" in lines[0]:
            text = "\n".join(lines[1:])

    return clean_text(_clean_nav_text(text))


def _extract_attachments(soup, detail_url: str) -> list[str]:
    """공지 본문 페이지에서 첨부파일 링크를 추출한다."""
    attachments = []
    seen = set()
    static_exts = [".pdf", ".hwp", ".doc", ".docx", ".xls", ".xlsx"]

    for a in soup.find_all("a", href=True):
        href = absolutize_href(a["href"], detail_url)
        if not href:
            continue

        is_static = any(href.lower().endswith(ext) for ext in static_exts)
        is_dynamic = "download" in href.lower() and (
            "atchmnflNo" in href or "fileNo" in href
        )

        if is_static or is_dynamic:
            label = clean_text(a.get_text(strip=True)) or "첨부파일"
            item = f"{label}: {href}"
            if item not in seen:
                seen.add(item)
                attachments.append(item)
    return attachments


def extract_notice_detail(detail_url: str, fallback_title: str = "") -> dict:
    """공지사항 본문 페이지에서 제목, 작성일, 본문, 첨부파일을 추출한다."""
    soup = fetch_html(detail_url)

    title = _extract_title(soup, detail_url, fallback_title)
    date = _extract_date(soup)
    content = _extract_content(soup, detail_url)
    attachments = _extract_attachments(soup, detail_url)

    # 본문이 너무 짧으면 첨부 PDF에서 텍스트 추출하여 보강
    if len(content.strip()) < 100:
        pdf_texts = []
        for att in attachments:
            if ".pdf" in att.lower():
                # "레이블: URL" 형태에서 URL 추출
                url = att.split(": ", 1)[-1]
                pdf_text = extract_pdf_text(url)
                if pdf_text:
                    pdf_texts.append(f"[첨부 PDF 내용]\n{pdf_text}")
                # 첫 번째 PDF만 사용 (속도/비용 고려)
                break
        if pdf_texts:
            content = content + "\n\n" + "\n\n".join(pdf_texts)

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
            detail = extract_notice_detail(item["url"], fallback_title=item["title"])
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
