"""
HTML 보고서 생성 모듈

Jinja2 템플릿을 활용하여 매물 분석 결과를 HTML 파일로 출력합니다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from naver_land import format_price, BASE_URL

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

TRADE_NAMES = {
    "A1": "매매",
    "B1": "전세",
    "B2": "월세",
}


def article_url(article_no: str) -> str:
    return f"{BASE_URL}/articles/{article_no}"


def generate_report(
    results: dict[str, list],
    config: dict,
    output_path: Path,
) -> None:
    """HTML 보고서 생성 및 저장"""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    env.filters["format_price"] = format_price

    template = env.get_template("report.html")

    html = template.render(
        generated_at=datetime.now().strftime("%Y년 %m월 %d일 %H:%M"),
        config=config,
        results=results,
        top_n=config["report"]["top_n"],
        trade_names=TRADE_NAMES,
        format_price=format_price,
        article_url=article_url,
    )

    output_path.write_text(html, encoding="utf-8")
    logger.info(f"보고서 저장 완료: {output_path}")
