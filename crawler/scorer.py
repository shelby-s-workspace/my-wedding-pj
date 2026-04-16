"""
매물 점수화 모듈

각 매물을 조건별로 평가하여 100점 만점의 종합 점수를 산출합니다.

[매매 점수 구성]
  가격      35점 — 6억에 가까울수록 만점, 10억에 가까울수록 0점 (선형)
  면적      30점 — 20평=기본 40%, 40평+=만점 (선형 증가)
  선호지역  20점 — 설정된 선호 구에 포함되면 만점
  역세권    15점 — API 태그에 역세권 키워드가 있으면 만점

[월세 점수 구성]
  월실부담금 35점 — 월세 + 보증금 기회비용(연 4%) 기준
  면적       30점 — 매매와 동일
  선호지역   20점 — 매매와 동일
  역세권     15점 — 매매와 동일
"""
from __future__ import annotations

from naver_land import parse_price, sqm_to_pyeong

SUBWAY_KEYWORDS = ["역세권", "지하철", "역 도보", "역근처", "역근방", "초역세권"]


# ──────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────

def _extract_district(address: str) -> str:
    """주소 문자열에서 구(區) 이름 추출"""
    for token in (address or "").split():
        if token.endswith("구"):
            return token
    return ""


def _parse_rent_price(price_str: str) -> tuple[int, int]:
    """월세 가격 문자열 → (보증금, 월세) 만원 단위 튜플

    예) "5,000/100"  → (5000, 100)
        "1억/80"     → (10000, 80)
    """
    if not price_str:
        return 0, 0
    if "/" in price_str:
        left, right = price_str.split("/", 1)
        return parse_price(left.strip()), parse_price(right.strip())
    return parse_price(price_str), 0


def _area_score(pyeong: float, max_weight: int) -> float:
    """면적 점수 계산

    20평 → 기본 40%, 40평 이상 → 만점, 그 사이 선형 증가
    """
    MIN_PY, MAX_PY = 20.0, 40.0
    if pyeong < MIN_PY:
        return 0.0
    if pyeong >= MAX_PY:
        return float(max_weight)
    ratio = (pyeong - MIN_PY) / (MAX_PY - MIN_PY)
    return round(max_weight * (0.4 + 0.6 * ratio), 1)


def _has_subway(tags) -> bool:
    """역세권 여부 판단 (태그 목록 기준)"""
    if not tags:
        return False
    joined = " ".join(str(t) for t in tags)
    return any(kw in joined for kw in SUBWAY_KEYWORDS)


def _get_pyeong(article: dict) -> float:
    """매물에서 평수 추출 (공급면적 우선, 없으면 전용면적)"""
    area2 = float(article.get("area2") or 0)  # 공급면적
    area1 = float(article.get("area1") or 0)  # 전용면적
    return sqm_to_pyeong(area2 if area2 > 0 else area1)


# ──────────────────────────────────────────
# 점수화 함수
# ──────────────────────────────────────────

def score_purchase(article: dict, config: dict, preferred: set) -> dict:
    """매매 매물 점수화 → 점수 딕셔너리 반환"""
    w = config["scoring"]["purchase"]
    p_cfg = config["search"]["purchase"]

    price_man = parse_price(article.get("dealOrWarrantPrc", ""))
    pyeong = _get_pyeong(article)
    district = _extract_district(article.get("exposureAddress", ""))
    has_sub = _has_subway(article.get("tagList"))

    # 1. 가격 점수 (낮을수록 유리)
    p_min, p_max = p_cfg["min_price"], p_cfg["max_price"]
    if price_man <= 0:
        price_score = 0.0
    elif price_man <= p_min:
        price_score = float(w["price"])
    elif price_man >= p_max:
        price_score = 0.0
    else:
        price_score = round(w["price"] * (p_max - price_man) / (p_max - p_min), 1)

    # 2. 면적 점수
    area_score = _area_score(pyeong, w["area"])

    # 3. 선호 지역 점수
    pref_score = float(w["preferred_district"]) if district in preferred else 0.0

    # 4. 역세권 점수
    subway_score = float(w["subway"]) if has_sub else 0.0

    total = price_score + area_score + pref_score + subway_score

    return {
        "total_score":    round(total, 1),
        "score_price":    price_score,
        "score_area":     area_score,
        "score_district": pref_score,
        "score_subway":   subway_score,
        "price_man":      price_man,
        "rent_man":       0,
        "monthly_cost":   0,
        "pyeong":         round(pyeong, 1),
        "district":       district,
        "has_subway":     has_sub,
        "is_preferred":   district in preferred,
    }


def score_monthly_rent(article: dict, config: dict, preferred: set) -> dict:
    """월세 매물 점수화 → 점수 딕셔너리 반환"""
    w = config["scoring"]["monthly_rent"]
    r_cfg = config["search"]["monthly_rent"]

    deposit_man, rent_man = _parse_rent_price(article.get("dealOrWarrantPrc", ""))
    pyeong = _get_pyeong(article)
    district = _extract_district(article.get("exposureAddress", ""))
    has_sub = _has_subway(article.get("tagList"))

    # 월 실부담금 = 월세 + 보증금 기회비용(연 4% / 12개월)
    opp_cost = (deposit_man * 0.04) / 12
    monthly_cost = rent_man + opp_cost

    max_monthly = r_cfg["max_rent"] + (r_cfg["max_deposit"] * 0.04 / 12)

    # 1. 월 부담금 점수 (낮을수록 유리)
    if monthly_cost <= 0:
        cost_score = 0.0
    elif monthly_cost <= max_monthly * 0.3:
        cost_score = float(w["rent_cost"])
    elif monthly_cost >= max_monthly * 1.5:
        cost_score = 0.0
    else:
        ratio = 1.0 - (monthly_cost / (max_monthly * 1.5))
        cost_score = round(w["rent_cost"] * max(ratio, 0), 1)

    # 2. 면적 점수
    area_score = _area_score(pyeong, w["area"])

    # 3. 선호 지역 점수
    pref_score = float(w["preferred_district"]) if district in preferred else 0.0

    # 4. 역세권 점수
    subway_score = float(w["subway"]) if has_sub else 0.0

    total = cost_score + area_score + pref_score + subway_score

    return {
        "total_score":    round(total, 1),
        "score_price":    cost_score,
        "score_area":     area_score,
        "score_district": pref_score,
        "score_subway":   subway_score,
        "price_man":      deposit_man,
        "rent_man":       rent_man,
        "monthly_cost":   round(monthly_cost),
        "pyeong":         round(pyeong, 1),
        "district":       district,
        "has_subway":     has_sub,
        "is_preferred":   district in preferred,
    }


def score_article(article: dict, config: dict, trade_type: str, preferred: set) -> dict:
    """거래 유형에 맞는 점수화 함수 호출"""
    if trade_type == "A1":
        return score_purchase(article, config, preferred)
    return score_monthly_rent(article, config, preferred)
