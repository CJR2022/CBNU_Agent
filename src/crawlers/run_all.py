"""전체 크롤링 실행 스크립트"""

import os
import sys

# 프로젝트 루트를 path에 추가해 server.py 임포트 가능하게 한다
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.crawlers.dorm_crawler import crawl_all_dorm_menus
from src.crawlers.notice_crawler import crawl_all_notices


def run_all():
    print("=== 공지사항 크롤링 시작 ===")
    crawl_all_notices()
    print("=== 기숙사 식단 크롤링 시작 ===")
    crawl_all_dorm_menus()
    print("=== 벡터스토어 재구축 시작 ===")
    from server import rebuild_vectorstore
    rebuild_vectorstore()
    print("=== 크롤링 및 벡터스토어 갱신 완료 ===")


if __name__ == "__main__":
    run_all()
