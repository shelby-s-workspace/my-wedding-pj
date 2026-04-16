"""
부동산 매물 분석 프로그램 — 진입점

[데이터 소스]
  직방(Zigbang) API — AWS EC2 환경에서 접근 가능

[실행 방법]
  py -m pip install -r requirements.txt
  py main.py

[출력]
  output/report_YYYYMMDD_HHMMSS.html — HTML 분석 보고서
  crawler.log                         — 실행 로그
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

from zigbang import ZigbangClient, SEOUL_DISTRICTS
from scorer import score_article
from report import generate_report

# ──────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crawler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
OUTPUT_DIR  = Path(__file__).parent / "output"

TRADE_LABEL = {"A1": "매매", "B1": "전세", "B2": "월세"}


# ──────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_articles(
    client: ZigbangClient,
    config: dict,
    trade_type: str,
) -> list[dict]:
    """서울 25개 구 전체에서 조건에 맞는 매물 수집 (중복 제거)"""
    search = config["search"]

    if trade_type == "A1":
        price_min = search["purchase"]["min_price"]
        price_max = search["purchase"]["max_price"]
    else:
        price_min = 0
        price_max = search["monthly_rent"]["max_deposit"]

    seen:     set[str]   = set()
    articles: list[dict] = []

    for district_query in SEOUL_DISTRICTS:
        district_name = district_query.replace("서울 ", "")
        logger.info(f"  [{district_name}] 검색 중...")

        # 1) 구 이름 → areaId
        area_id = client.get_area_id(district_query)
        if not area_id:
            logger.warning(f"    → areaId 없음, 건너뜀")
            continue

        # 2) areaId → 매물 목록
        items = client.fetch_items(
            area_id=area_id,
            trade_type=trade_type,
            price_min=price_min,
            price_max=price_max,
            area_min_sqm=search["min_area_sqm"],
        )

        new_cnt = 0
        for art in items:
            art_no = art.get("articleNo", "")
            if art_no and art_no not in seen:
                seen.add(art_no)
                articles.append(art)
                new_cnt += 1

        if new_cnt:
            logger.info(f"    → {new_cnt}건 신규 (누적 {len(articles)}건)")

    return articles


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────

def main() -> None:
    config = load_config()
    OUTPUT_DIR.mkdir(exist_ok=True)

    preferred   = set(config["search"]["preferred_districts"])
    trade_types = config["search"]["trade_types"]
    all_results: dict[str, list] = {}

    with ZigbangClient() as client:
        if not client.test_connection():
            logger.error("직방 API 연결 실패. 네트워크를 확인하세요.")
            sys.exit(1)

        for trade_type in trade_types:
            label = TRADE_LABEL.get(trade_type, trade_type)
            logger.info(f"\n{'=' * 50}")
            logger.info(f"  [{label}] 수집 시작 — 서울 전체 25개 구")
            logger.info(f"{'=' * 50}")

            articles = collect_articles(client, config, trade_type)
            logger.info(f"\n[{label}] 총 {len(articles)}건 → 점수화 중...")

            scored = [
                {**art, **score_article(art, config, trade_type, preferred)}
                for art in articles
            ]
            scored.sort(key=lambda x: x["total_score"], reverse=True)
            all_results[trade_type] = scored

            logger.info(
                f"[{label}] 완료 | "
                f"최고점: {scored[0]['total_score'] if scored else '-'} | "
                f"선호지역: {sum(1 for a in scored if a['is_preferred'])}건"
            )

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = OUTPUT_DIR / f"report_{timestamp}.html"
    generate_report(all_results, config, report_path)

    logger.info(f"\n✓ 보고서 생성 완료")
    print(f"\n  보고서 위치: {report_path.resolve()}")


if __name__ == "__main__":
    main()
