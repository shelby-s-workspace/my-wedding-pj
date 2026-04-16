"""
직방(Zigbang) API 클라이언트

https://www.zigbang.com 의 비공개 API를 사용합니다.
직방은 AWS 인프라를 자체 사용하므로 EC2 환경에서도 접근 가능합니다.

[검색 흐름]
  1. 구 이름 → /v2/search  → areaId 획득
  2. areaId  → /v2/items   → 매물 목록 획득
  3. 매물 데이터 → normalize_item() → 공통 포맷으로 변환
     (scorer.py · report.html이 기대하는 필드명과 동일하게 맞춤)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.zigbang.com"

HEADERS: dict[str, str] = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Connection":      "keep-alive",
    "Origin":          "https://www.zigbang.com",
    "Referer":         "https://www.zigbang.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# 서울 25개 구 검색 쿼리
SEOUL_DISTRICTS: list[str] = [
    "서울 종로구", "서울 중구",   "서울 용산구",  "서울 성동구",
    "서울 광진구", "서울 동대문구","서울 중랑구",  "서울 성북구",
    "서울 강북구", "서울 도봉구", "서울 노원구",  "서울 은평구",
    "서울 서대문구","서울 마포구", "서울 양천구",  "서울 강서구",
    "서울 구로구", "서울 금천구", "서울 영등포구","서울 동작구",
    "서울 관악구", "서울 서초구", "서울 강남구",  "서울 송파구",
    "서울 강동구",
]


# ──────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────

def _to_korean_price(price_man: int) -> str:
    """만원 정수 → 한국 가격 문자열  (8억5,000  /  6억  /  3,000만)"""
    if price_man <= 0:
        return "0"
    eok, rem = divmod(price_man, 10000)
    if eok and rem:
        return f"{eok}억{rem:,}"
    if eok:
        return f"{eok}억"
    return f"{price_man:,}"


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_item(raw: dict, trade_type: str) -> dict:
    """직방 응답 → scorer.py / report.html 공통 포맷

    직방 API가 반환하는 필드명은 버전마다 다를 수 있어
    여러 후보 키를 순서대로 시도합니다.
    """
    def pick(*keys):
        for k in keys:
            v = raw.get(k)
            if v is not None:
                return v
        return None

    # 가격 (만원 단위)
    if trade_type == "A1":  # 매매
        price_man = _safe_int(pick("price", "dealPrice", "salePrice", "매매가"))
        price_str = _to_korean_price(price_man)
    else:  # 월세
        deposit   = _safe_int(pick("deposit", "보증금"))
        monthly   = _safe_int(pick("monthlyRent", "rent", "월세"))
        price_man = deposit
        price_str = f"{_to_korean_price(deposit)}/{_to_korean_price(monthly)}"

    # 면적
    area1 = _safe_float(pick("exclusiveArea", "area", "전용면적", "전용"))
    area2 = _safe_float(pick("supplyArea", "공급면적", "공급"))
    if area2 == 0 and area1 > 0:
        area2 = round(area1 * 1.3, 2)   # 공급면적 없으면 전용의 130%로 추정

    # 주소 / 이름
    address = str(pick("address", "지번주소", "roadAddress", "도로명주소") or "")
    name    = str(pick("buildingName", "complexName", "name", "단지명", "건물명") or "")
    floor   = str(pick("floor", "층") or "")

    # 역세권 태그 추출
    tags: list[str] = []
    desc = str(pick("description", "특징", "memo") or "")
    if any(kw in desc for kw in ["역세권", "역", "지하철"]):
        tags.append("역세권")
    if raw.get("isSubwayWalk") or raw.get("subwayDistance"):
        tags.append("역세권")

    return {
        "articleNo":          str(pick("itemId", "id") or ""),
        "articleName":        name,
        "buildingName":       name,
        "exposureAddress":    address,
        "dealOrWarrantPrc":   price_str,
        "area1":              area1,
        "area2":              area2,
        "floor":              floor,
        "realEstateTypeName": str(pick("roomTypeName", "buildingType", "roomType") or "아파트"),
        "tradeTypeName":      "매매" if trade_type == "A1" else "월세",
        "tagList":            tags,
    }


# ──────────────────────────────────────────
# 클라이언트
# ──────────────────────────────────────────

class ZigbangClient:
    """직방 API 클라이언트"""

    def __init__(self, request_delay: float = 0.5) -> None:
        self.delay = request_delay
        self.client = httpx.Client(
            headers=HEADERS,
            timeout=20,
            follow_redirects=True,
        )
        self._area_cache: dict[str, str] = {}

    # ── 내부 헬퍼 ─────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Optional[dict | list]:
        time.sleep(self.delay)
        try:
            resp = self.client.get(f"{BASE_URL}{path}", params=params or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP {e.response.status_code} ← {path}")
            return None
        except httpx.TimeoutException:
            logger.warning(f"Timeout ← {path}")
            return None
        except Exception as e:
            logger.warning(f"오류: {e} ← {path}")
            return None

    # ── 공개 메서드 ──────────────────────────

    def get_area_id(self, district_query: str) -> Optional[str]:
        """구 이름으로 직방 areaId 조회 (캐시)"""
        if district_query in self._area_cache:
            return self._area_cache[district_query]

        data = self._get("/v2/search", {"leaseYn": "N", "q": district_query})
        if not data:
            return None

        rows = data if isinstance(data, list) else (
            data.get("items") or data.get("results") or data.get("data") or []
        )

        # 타입이 지역(구/동)인 항목 우선 선택
        REGION_TYPES = {"법정동", "동", "구", "region", "area", "district"}
        for row in rows:
            if str(row.get("type", "")).lower() in REGION_TYPES:
                aid = str(row.get("id") or row.get("areaId") or "")
                if aid:
                    self._area_cache[district_query] = aid
                    return aid

        # fallback: 첫 번째 결과
        if rows:
            aid = str(rows[0].get("id") or rows[0].get("areaId") or "")
            if aid:
                self._area_cache[district_query] = aid
                return aid

        logger.warning(f"areaId 없음: {district_query}")
        return None

    def fetch_items(
        self,
        area_id: str,
        trade_type: str = "A1",
        price_min: int = 0,
        price_max: int = 0,
        area_min_sqm: int = 0,
    ) -> list[dict]:
        """areaId 기반 매물 목록 조회 → 공통 포맷 리스트 반환"""
        service_type = "buy" if trade_type == "A1" else "rent"

        params = {
            "domain":            "zigbang",
            "areaId":            area_id,
            "serviceType":       service_type,
            "depositMin":        price_min,
            "depositMax":        price_max,
            "priceMin":          price_min,
            "priceMax":          price_max,
            "exclusiveAreaMin":  area_min_sqm,
            "checkAnyItemWithoutFilter": False,
        }

        data = self._get("/v2/items", params)
        if data is None:
            return []

        rows = data if isinstance(data, list) else (
            data.get("items") or data.get("data") or data.get("list") or []
        )
        return [normalize_item(r, trade_type) for r in rows]

    def test_connection(self) -> bool:
        """강남구 검색으로 연결 확인"""
        logger.info("직방 API 연결 테스트 중...")
        try:
            resp = self.client.get(
                f"{BASE_URL}/v2/search",
                params={"leaseYn": "N", "q": "서울 강남구"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"연결 성공 (HTTP {resp.status_code})")
                return True
            logger.error(f"연결 실패: HTTP {resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"연결 실패: {e}")
            return False

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ZigbangClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
