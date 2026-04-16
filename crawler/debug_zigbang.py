"""
직방 API 연결 진단 스크립트

실행: py debug_zigbang.py
"""
import json
import httpx

BASE = "https://apis.zigbang.com"
HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Origin":          "https://www.zigbang.com",
    "Referer":         "https://www.zigbang.com/",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
}


def sep(title=""):
    print(f"\n{'='*55}")
    if title:
        print(f"  {title}")
        print("=" * 55)


def show(resp):
    print(f"  상태: HTTP {resp.status_code}")
    try:
        body = resp.json()
        preview = json.dumps(body, ensure_ascii=False, indent=2)
        lines = preview.split("\n")
        print("  응답 구조 (처음 30줄):")
        for line in lines[:30]:
            print("  " + line)
        if len(lines) > 30:
            print(f"  ... (총 {len(lines)}줄)")
    except Exception:
        print("  응답(텍스트):", resp.text[:300])


client = httpx.Client(headers=HEADERS, timeout=10, follow_redirects=True)

# ──────────────────────────────────────────
sep("1. 직방 기본 연결 확인")
try:
    r = client.get("https://www.zigbang.com/")
    print(f"  www.zigbang.com  → HTTP {r.status_code}")
except Exception as e:
    print(f"  www.zigbang.com  → 실패: {e}")

try:
    r = client.get(f"{BASE}/")
    print(f"  apis.zigbang.com → HTTP {r.status_code}")
except Exception as e:
    print(f"  apis.zigbang.com → 실패: {e}")

# ──────────────────────────────────────────
sep("2. 지역 검색 API  (/v2/search?q=서울 강남구)")
try:
    r = client.get(f"{BASE}/v2/search", params={"leaseYn": "N", "q": "서울 강남구"})
    show(r)
except Exception as e:
    print(f"  실패: {e}")

# ──────────────────────────────────────────
sep("3. 매물 조회 API  (/v2/items) — areaId 방식")
try:
    r = client.get(f"{BASE}/v2/items", params={
        "domain":      "zigbang",
        "areaId":      "11680",   # 강남구 추정 코드
        "serviceType": "buy",
        "priceMin":    60000,
        "priceMax":    100000,
        "checkAnyItemWithoutFilter": False,
    })
    show(r)
except Exception as e:
    print(f"  실패: {e}")

# ──────────────────────────────────────────
sep("4. 매물 조회 API  (/v2/items) — geohash 방식")
try:
    r = client.get(f"{BASE}/v2/items", params={
        "domain":   "zigbang",
        "geohash":  "wydmd",   # 서울 강남 일대 geohash
        "serviceType": "buy",
    })
    show(r)
except Exception as e:
    print(f"  실패: {e}")

# ──────────────────────────────────────────
sep("5. 아파트 단지 검색  (/property/complexes)")
try:
    r = client.get(f"{BASE}/property/complexes", params={"q": "강남구", "serviceType": "buy"})
    show(r)
except Exception as e:
    print(f"  실패: {e}")

sep("진단 완료 — 위 결과를 공유해주세요")
client.close()
