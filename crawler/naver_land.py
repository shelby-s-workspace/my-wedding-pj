"""
네이버 부동산(new.land.naver.com) API 클라이언트

네이버페이 부동산으로 통합된 이후에도 동일한 API 엔드포인트를 사용합니다.
공식 API가 아니므로 브라우저 요청과 동일한 헤더를 전송합니다.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://new.land.naver.com"
API_BASE = f"{BASE_URL}/api"

# 브라우저와 동일한 헤더 구성
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Referer": "https://new.land.naver.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# 서울특별시 25개 구 cortarNo 코드
DISTRICT_CODES: dict[str, str] = {
    "종로구":   "1111000000",
    "중구":     "1114000000",
    "용산구":   "1117000000",
    "성동구":   "1120000000",
    "광진구":   "1121500000",
    "동대문구": "1123000000",
    "중랑구":   "1126000000",
    "성북구":   "1129000000",
    "강북구":   "1130500000",
    "도봉구":   "1132000000",
    "노원구":   "1135000000",
    "은평구":   "1138000000",
    "서대문구": "1141000000",
    "마포구":   "1144000000",
    "양천구":   "1147000000",
    "강서구":   "1150000000",
    "구로구":   "1153000000",
    "금천구":   "1154500000",
    "영등포구": "1156000000",
    "동작구":   "1159000000",
    "관악구":   "1162000000",
    "서초구":   "1165000000",
    "강남구":   "1168000000",
    "송파구":   "1171000000",
    "강동구":   "1174000000",
}

# 검색할 건물 유형 (아파트, 오피스텔, 아파트분양권, 빌라/연립)
REAL_ESTATE_TYPES = "APT:OPST:ABYG:VL"


# ──────────────────────────────────────────
# 유틸리티 함수
# ──────────────────────────────────────────

def parse_price(price_str: str) -> int:
    """한국 가격 문자열을 만원 단위 정수로 변환

    예)
        "8억5,000"  → 85000
        "6억"       → 60000
        "3,000"     → 3000
        "100"       → 100
    """
    if not price_str or price_str in ("-", "0", ""):
        return 0
    s = price_str.replace(",", "").replace(" ", "")
    total = 0
    if "억" in s:
        parts = s.split("억", 1)
        try:
            total += int(parts[0]) * 10000
            if parts[1]:
                total += int(parts[1])
        except ValueError:
            pass
    else:
        try:
            total = int(s)
        except ValueError:
            pass
    return total


def sqm_to_pyeong(sqm: float) -> float:
    """㎡ → 평 변환 (1평 = 3.3058㎡)"""
    return sqm / 3.3058 if sqm > 0 else 0.0


def format_price(price_man: int) -> str:
    """만원 단위 정수를 한국 가격 형식 문자열로 변환

    예)
        85000 → "8억 5,000만"
        60000 → "6억"
        3000  → "3,000만"
    """
    if price_man <= 0:
        return "-"
    eok, rem = divmod(price_man, 10000)
    if eok > 0 and rem > 0:
        return f"{eok}억 {rem:,}만"
    if eok > 0:
        return f"{eok}억"
    return f"{price_man:,}만"


# ──────────────────────────────────────────
# API 클라이언트
# ──────────────────────────────────────────

class NaverLandClient:
    """네이버 부동산 비공개 API 클라이언트"""

    def __init__(self, auth: dict | None = None, request_delay: float = 0.6) -> None:
        self.delay = request_delay
        self.client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=30,
            follow_redirects=True,
        )
        if auth:
            self._apply_auth(auth)
        else:
            logger.warning("auth.yaml 없음 — 인증 없이 시도 (차단될 수 있음)")

    def _apply_auth(self, auth: dict) -> None:
        """auth.yaml에서 읽은 인증 정보를 클라이언트에 적용"""
        PLACEHOLDER = "여기에"

        authorization = auth.get("authorization", "")
        if authorization and PLACEHOLDER not in authorization:
            self.client.headers["Authorization"] = authorization
            logger.info("Authorization 헤더 적용 완료")
        else:
            logger.warning("Authorization 값이 없거나 미입력 상태")

        cookies = auth.get("cookies") or {}
        valid = {k: v for k, v in cookies.items() if v and PLACEHOLDER not in str(v)}
        if valid:
            cookie_str = "; ".join(f"{k}={v}" for k, v in valid.items())
            self.client.headers["Cookie"] = cookie_str
            logger.info(f"쿠키 적용 완료: {list(valid.keys())}")
        else:
            logger.warning("유효한 쿠키 없음 — auth.yaml을 확인하세요")

    def test_connection(self) -> bool:
        """강남구 소량 조회로 API 연결 확인"""
        logger.info("API 연결 테스트 중 (강남구)...")
        data = self.fetch_page(
            cortar_no="1168000000",
            trade_type="A1",
            price_min=60000,
            price_max=100000,
            area_min=49,
            page=1,
        )
        if data is not None and "articles" in data:
            count = len(data.get("articles") or [])
            logger.info(f"연결 테스트 성공 — 강남구 매물 {count}건 수신")
            return True
        logger.error("연결 테스트 실패 — crawler/auth.yaml 값을 확인하세요")
        return False

    def _get(self, url: str, params: dict) -> Optional[dict]:
        """GET 요청 with 에러 처리 및 재시도"""
        for attempt in range(1, 3):
            try:
                time.sleep(self.delay)
                resp = self.client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code in (401, 403):
                    logger.error(
                        f"API 접근 거부 (HTTP {code}). "
                        "브라우저로 new.land.naver.com을 방문한 후 재시도하세요."
                    )
                    return None
                logger.warning(f"HTTP {code} — 재시도 {attempt}/2")
            except httpx.RequestError as e:
                logger.warning(f"네트워크 오류: {e} — 재시도 {attempt}/2")
        return None

    def fetch_page(
        self,
        cortar_no: str,
        trade_type: str,
        price_min: int = 0,
        price_max: int = 0,
        area_min: int = 0,
        page: int = 1,
    ) -> Optional[dict]:
        """단일 페이지 매물 조회"""
        params = {
            "cortarNo":           cortar_no,
            "order":              "rank",
            "realEstateType":     REAL_ESTATE_TYPES,
            "tradeType":          trade_type,
            "tag":                ":::::::::",
            "rentPriceMin":       0,
            "rentPriceMax":       900000,
            "priceMin":           price_min,
            "priceMax":           price_max,
            "areaMin":            area_min,
            "areaMax":            "",
            "oldBuildYear":       "",
            "recentlyBuildYear":  "",
            "minHouseHoldCount":  "",
            "maxHouseHoldCount":  "",
            "showArticle":        "false",
            "sameAddressGroup":   "false",
            "minMaintenanceCost": "",
            "maxMaintenanceCost": "",
            "startDateMove":      "",
            "endDateMove":        "",
            "page":               page,
            "pageSize":           20,
        }
        return self._get(f"{API_BASE}/articles", params)

    def fetch_all(
        self,
        cortar_no: str,
        trade_type: str,
        price_min: int = 0,
        price_max: int = 0,
        area_min: int = 0,
        max_pages: int = 5,
    ) -> list[dict]:
        """구 단위로 모든 페이지 매물 수집"""
        articles: list[dict] = []
        for page in range(1, max_pages + 1):
            data = self.fetch_page(
                cortar_no=cortar_no,
                trade_type=trade_type,
                price_min=price_min,
                price_max=price_max,
                area_min=area_min,
                page=page,
            )
            if data is None:
                break
            page_articles = data.get("articles") or []
            articles.extend(page_articles)
            if not data.get("isMoreData", False) or not page_articles:
                break
        return articles

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "NaverLandClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
