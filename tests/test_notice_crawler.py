"""notice_crawler 모듈 단위 테스트"""

from bs4 import BeautifulSoup

from src.crawlers.notice_crawler import _extract_attachments


def test_extract_attachments_includes_dynamic_download_links():
    """동적 첨부파일 다운로드 링크를 추출한다."""
    html = """
    <html><body>
        <a href="/downloadBbsFile.do?atchmnflNo=12345">학사일정.hwp</a>
        <a href="/common/fileDownload.do?fileNo=67890">장학신청서.pdf</a>
        <a href="/selectBbsNttView.do?bbsNo=8&nttNo=1">공지 제목</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    detail_url = "https://www.chungbuk.ac.kr/www/selectBbsNttView.do?bbsNo=8&nttNo=1"

    attachments = _extract_attachments(soup, detail_url)
    hrefs = [att.split(": ", 1)[-1] for att in attachments]

    assert any("downloadBbsFile.do?atchmnflNo=12345" in href for href in hrefs)
    assert any("fileDownload.do?fileNo=67890" in href for href in hrefs)
    assert all("selectBbsNttView" not in href for href in hrefs)


def test_extract_attachments_keeps_static_file_links():
    """기존 정적 파일 확장자 링크 추출을 유지한다."""
    html = """
    <html><body>
        <a href="/files/notice.pdf">공지문</a>
        <a href="/board/read?nttNo=2">두 번째 공지</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    detail_url = "https://example.com/board/read?nttNo=1"

    attachments = _extract_attachments(soup, detail_url)
    hrefs = [att.split(": ", 1)[-1] for att in attachments]

    assert any(href.endswith("/files/notice.pdf") for href in hrefs)
    assert all("/board/read" not in href for href in hrefs)


def test_extract_attachments_includes_dorm_dynamic_pdf_links():
    """기숙사 동적 다운로드 링크 중 PDF 라벨을 가진 링크를 추출한다."""
    html = """
    <html><body>
        <a href="/home/sub.php?menukey=20039&bid=1&download=1&fno=1">입퇴거 안내.pdf</a>
        <a href="/home/sub.php?menukey=20039&bid=1&download=1&fno=2">공지 목록</a>
        <a href="/home/sub.php?menukey=20039&bbs.php=1&download=1&bid=1">선착순 신청.hwp</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    detail_url = "https://dorm.chungbuk.ac.kr/home/sub.php?menukey=20039&bid=1"

    attachments = _extract_attachments(soup, detail_url)
    hrefs = [att.split(": ", 1)[-1] for att in attachments]
    labels = [att.split(": ", 1)[0] for att in attachments]

    assert any("fno=1" in href for href in hrefs)
    assert any(".pdf" in label for label in labels)
    assert all("fno=2" not in href for href in hrefs)
    assert all("bbs.php" not in href for href in hrefs)
