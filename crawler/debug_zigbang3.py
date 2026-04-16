"""
직방 API 3차 진단 — /v3/items 파라미터 탐색

실행: py debug_zigbang3.py
"""
import json
import httpx
from collections import Counter

BASE = "https://apis.zigbang.com"
HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Origin":          "https://www.zigbang.com",
    "Referer":         "https://www.zigbang.com/",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
}
client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)


def sep(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print("=" * 60)


def show_json(data, lines=30):
    txt = json.dumps(data, ensure_ascii=False, indent=2).split("\n")
    for l in txt[:lines]:
        print("  " + l)
    if len(txt) > lines:
        print(f"  ... (총 {len(txt)}줄 생략)")


def try_get(path, params=None, label=None):
    params = params or {}
    label = label or f"{path} {params}"
    try:
        r = client.get(f"{BASE}{path}", params=params, timeout=8)
        items_count = None
        if r.status_code == 200:
            try:
                body = r.json()
                if isinstance(body, dict):
                    lst = body.get("items") or body.get("list") or body.get("data") or []
                    items_count = len(lst) if isinstance(lst, list) else "?"
                elif isinstance(body, list):
                    items_count = len(body)
            except Exception:
                pass
        cnt_str = f" → {items_count}건" if items_count is not None else ""
        print(f"  HTTP {r.status_code}{cnt_str}  ← {label}")
        return r
    except Exception as e:
        print(f"  오류: {e}  ← {label}")
        return None


# ─────────────────────────────────────────────────
# Step 1: 강남구 검색 → apartment 단지 ID 수집
# ─────────────────────────────────────────────────
sep("STEP 1. 강남구 검색 → 아파트 단지 ID 수집")
r = client.get(f"{BASE}/v2/search", params={"leaseYn": "N", "q": "서울 강남구"})
items_search = r.json().get("items", [])
apt_items = [i for i in items_search if i.get("type") == "apartment"]
print(f"  apartment 타입 {len(apt_items)}개")

# 대형 단지 위주로 5개 선택
sample_ids = [i["id"] for i in apt_items[:5]]
print(f"  샘플 단지 ID: {sample_ids}")

# 첫 번째 단지 상세 확인
if apt_items:
    print(f"\n  첫 번째 단지 전체 데이터:")
    show_json(apt_items[0], 40)


# ─────────────────────────────────────────────────
# Step 2: /v3/items — complexId / apartmentId 파라미터 시도
# ─────────────────────────────────────────────────
sep("STEP 2. /v3/items 파라미터 탐색")

if sample_ids:
    cid = sample_ids[0]  # 첫 번째 단지 ID
    print(f"  단지 ID {cid} 기준 매물 조회 시도:\n")

    tests = [
        ("/v3/items", {"complexId":    cid}),
        ("/v3/items", {"complexId":    cid, "serviceType": "buy"}),
        ("/v3/items", {"complexId":    cid, "serviceType": "rent"}),
        ("/v3/items", {"complexId":    cid, "serviceType": "buy", "domain": "zigbang"}),
        ("/v3/items", {"apartmentId":  cid}),
        ("/v3/items", {"aptId":        cid}),
        ("/v3/items", {"buildingId":   cid}),
        ("/v3/items", {"itemId":       cid}),
        ("/v3/items/complexes", {"complexId": cid}),
        (f"/v3/items/complexes/{cid}", {}),
        (f"/v3/complexes/{cid}",        {}),
        (f"/v3/complexes/{cid}/items",  {}),
        (f"/v2/complexes/{cid}/items",  {"serviceType": "buy"}),
        (f"/v3/apt/{cid}/items",        {}),
    ]
    for path, params in tests:
        try_get(path, params, label=f"{path}?{'&'.join(f'{k}={v}' for k,v in params.items())}")


# ─────────────────────────────────────────────────
# Step 3: /v3/items — geohash 파라미터 시도
# ─────────────────────────────────────────────────
sep("STEP 3. /v3/items — geohash 방식 탐색")

# 강남구 일대 geohash (정밀도 4~5)
# 37.48, 127.08 부근
GEOHASHES = [
    "wydm",    # 강남 일대 (4자리)
    "wydmd",   # 강남 더 좁게 (5자리)
    "wydjx",   # 강남구청 인근
    "wydmf",
    "wydme",
    "wydn",
]

for gh in GEOHASHES:
    tests_gh = [
        {"geohash": gh},
        {"geohash": gh, "serviceType": "buy"},
        {"geohash": gh, "serviceType": "buy", "domain": "zigbang"},
    ]
    for p in tests_gh:
        r = try_get("/v3/items", p, label=f"/v3/items {p}")
        if r and r.status_code == 200:
            body = r.json()
            lst = body.get("items") or body.get("list") or []
            if lst:
                print(f"\n    ★★ 매물 발견! 첫 번째 항목:")
                show_json(lst[0], 20)
                break
    else:
        continue
    break


# ─────────────────────────────────────────────────
# Step 4: /v3/items — areaId 파라미터 시도
# ─────────────────────────────────────────────────
sep("STEP 4. /v3/items — areaId 방식 탐색")

# /v2/search에서 address 타입 id (강남구 areaId)
area_item = next((i for i in items_search if i.get("type") == "address"), None)
if area_item:
    area_id = area_item["id"]
    print(f"  강남구 areaId: {area_id} (name={area_item.get('name')})\n")

    for p in [
        {"areaId": area_id},
        {"areaId": area_id, "serviceType": "buy"},
        {"areaId": area_id, "serviceType": "buy", "domain": "zigbang"},
        {"areaId": area_id, "serviceType": "buy", "realEstateType": "아파트"},
        {"areaId": area_id, "serviceType": "buy", "type": "apartment"},
    ]:
        r = try_get("/v3/items", p, label=f"/v3/items {p}")
        if r and r.status_code == 200:
            body = r.json()
            lst = body.get("items") or body.get("list") or []
            if lst:
                print(f"\n    ★★ 매물 발견! 첫 번째 항목:")
                show_json(lst[0], 20)


# ─────────────────────────────────────────────────
# Step 5: 직방 앱 실제 사용 패턴 — otp/token 필요 여부 확인
# ─────────────────────────────────────────────────
sep("STEP 5. 인증 토큰 필요 여부 확인")

# /v3/items에 아무 파라미터도 없이 → 응답 헤더/상태 확인
r = client.get(f"{BASE}/v3/items", timeout=5)
print(f"  /v3/items (no params)  → HTTP {r.status_code}")
print(f"  Content-Type: {r.headers.get('content-type', 'N/A')}")
print(f"  응답 바디: {r.text[:200]}")

# 매물 리스트 전용 엔드포인트 추가 탐색
sep("STEP 6. 추가 엔드포인트 탐색")
MORE = [
    ("/v2/items/apt",          {"areaId": "8192", "serviceType": "buy"}),
    ("/v2/oapi/items",         {"areaId": "8192"}),
    ("/v1/items",              {"areaId": "8192", "serviceType": "buy"}),
    ("/v3/items/apt",          {"areaId": "8192", "serviceType": "buy"}),
    ("/v3/apt/items",          {"areaId": "8192", "serviceType": "buy"}),
    ("/property/items",        {"areaId": "8192", "serviceType": "buy"}),
    ("/v2/items",              {"areaId": "8192", "serviceType": "buy", "domain": "zigbang"}),
    ("/v2/items",              {"areaId": "8192", "checkAnyItemWithoutFilter": "true"}),
]
for path, params in MORE:
    r = try_get(path, params, label=f"{path} {params}")
    if r and r.status_code == 200:
        body = r.json()
        lst = (body.get("items") or body.get("list") or body.get("data")
               if isinstance(body, dict) else body)
        if lst:
            print(f"\n    ★★ 매물 발견! 첫 번째 항목:")
            show_json(lst[0] if isinstance(lst, list) else lst, 20)

sep("3차 진단 완료")
client.close()
