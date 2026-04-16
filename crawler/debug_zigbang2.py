"""
직방 API 2차 진단 — 타입 분석 + 신규 엔드포인트 탐색

실행: py debug_zigbang2.py
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
    print(f"\n{'='*55}")
    if title:
        print(f"  {title}")
        print("=" * 55)


def show_json(data, lines=25):
    txt = json.dumps(data, ensure_ascii=False, indent=2).split("\n")
    for l in txt[:lines]:
        print("  " + l)
    if len(txt) > lines:
        print(f"  ... (총 {len(txt)}줄 생략)")


# ──────────────────────────────────────────
sep("1. 검색 응답 타입 분석 (서울 강남구)")
r = client.get(f"{BASE}/v2/search", params={"leaseYn": "N", "q": "서울 강남구"})
data = r.json()
items = data.get("items", [])
type_counts = Counter(i.get("type", "없음") for i in items)
print(f"  총 {len(items)}개 항목, 타입별 분류:")
for t, cnt in type_counts.most_common():
    sample = next(i for i in items if i.get("type") == t)
    print(f"    [{t}] {cnt}개  예) id={sample.get('id')} name={sample.get('name')}")

# 아파트/단지 타입 샘플 전체 출력
APT_TYPES = {"apt", "complex", "apartment", "단지", "아파트", "오피스텔", "officetel"}
for t in type_counts:
    if any(a in str(t).lower() for a in APT_TYPES):
        print(f"\n  ★ 아파트 관련 타입 [{t}] 샘플:")
        sample = next(i for i in items if i.get("type") == t)
        show_json(sample, 20)


# ──────────────────────────────────────────
sep("2. 아파트 단지명으로 직접 검색")
r2 = client.get(f"{BASE}/v2/search", params={"leaseYn": "N", "q": "래미안 강남"})
data2 = r2.json()
items2 = data2.get("items", [])
type_counts2 = Counter(i.get("type", "없음") for i in items2)
print(f"  '래미안 강남' 검색 → 타입별:")
for t, cnt in type_counts2.most_common():
    sample = next(i for i in items2 if i.get("type") == t)
    print(f"    [{t}] {cnt}개  예) id={sample.get('id')} name={sample.get('name')}")


# ──────────────────────────────────────────
sep("3. 신규 엔드포인트 탐색")
CANDIDATES = [
    ("/v2/complexes",                    {"q": "강남구"}),
    ("/v2/apt/items",                    {"areaId": "11680"}),
    ("/v3/items",                        {"domain": "zigbang", "areaId": "11680"}),
    ("/v3/search",                       {"q": "서울 강남구"}),
    ("/v2/items/list",                   {"domain": "zigbang"}),
    ("/v2/buildings",                    {"q": "강남구"}),
    ("/search/complexes",                {"q": "강남구"}),
    ("/v2/realestate/complexes",         {"q": "강남구"}),
]
for path, params in CANDIDATES:
    try:
        r = client.get(f"{BASE}{path}", params=params, timeout=5)
        print(f"  {path:40s} → HTTP {r.status_code}")
        if r.status_code == 200:
            try:
                body = r.json()
                print(f"    ★ 200! 키 목록: {list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
                show_json(body, 10)
            except Exception:
                print(f"    응답: {r.text[:200]}")
    except Exception as e:
        print(f"  {path:40s} → 오류: {e}")


# ──────────────────────────────────────────
# 1번 검색에서 아파트 타입 id 찾으면 상세 조회 시도
sep("4. 검색 결과 id로 상세/매물 조회 시도")
for item in items[:5]:
    iid = item.get("id")
    itype = item.get("type")
    for detail_path in [f"/v2/items/{iid}", f"/v2/complexes/{iid}", f"/v2/complexes/{iid}/items"]:
        try:
            r = client.get(f"{BASE}{detail_path}", timeout=5)
            if r.status_code == 200:
                print(f"  ★ {detail_path} → HTTP 200")
                show_json(r.json(), 15)
        except Exception:
            pass

sep("2차 진단 완료")
client.close()
