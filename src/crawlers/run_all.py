"""전체 크롤링 실행 스크립트"""

from src.crawlers.dorm_crawler import crawl_all_dorm_menus
from src.crawlers.notice_crawler import crawl_all_notices


def run_all():
    print("=== 공지사항 크롤링 시작 ===")
    crawl_all_notices()
    print("=== 기숙사 식단 크롤링 시작 ===")
    crawl_all_dorm_menus()
    print("=== 크롤링 완료 ===")


if __name__ == "__main__":
    run_all()
