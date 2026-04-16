"""
직방 API 4차 진단 — 인증 토큰 + 원룸 검증 + 서브도메인 탐색

가설:
  - /v3/items 는 원룸/오피스텔 전용 (아파트는 별도 경로)
  - 아파트 매물 API는 인증 토큰 또는 다른 도메인 필요

실행: py debug_zigbang4.py
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
client = httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True)


def sep(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print("=" * 60)


def show_json(data, lines=25):
    txt = json.dumps(data, ensure_ascii=False, indent=2).split("\n")
    for l in txt[:lines]:
        print("  " + l)
    if len(txt) > lines:
        print(f"  ... (총 {len(txt)}줄 생략)")


def try_url(url, params=None, headers_extra=None, method="GET", label=None):
    h = dict(client.headers)
    if headers_extra:
        h.update(headers_extra)
    label = label or url
    try:
        if method == "POST":
            r = httpx.post(url, headers=h, json=params or {}, timeout=8, follow_redirects=True)
        else:
            r = httpx.get(url, headers=h, params=params or {}, timeout=8, follow_redirects=True)

        count = None
        if r.status_code == 200:
            try:
                body = r.json()
                if isinstance(body, dict):
                    lst = body.get("items") or body.get("list") or body.get("data") or []
                    count = len(lst) if isinstance(lst, list) else "?"
                elif isinstance(body, list):
                    count = len(body)
            except Exception:
                pass

        cnt_str = f" → {count}건" if count is not None else ""
        print(f"  HTTP {r.status_code}{cnt_str}  ← {label}")
        return r
    except Exception as e:
        print(f"  오류: {e}  ← {label}")
        return None


# ─────────────────────────────────────────────────────────
sep("STEP 1. /v3/items 원룸 검증 (서울 강남역 주변)")
# 강남역 위경도: 37.4979, 127.0276 → geohash ≈ wydmc
# 만약 원룸 전용 엔드포인트라면 이 파라미터로 데이터가 나와야 함

ROOM_GEOHASHES = ["wydmc", "wydm5", "wydmg", "wydmh", "wydjz"]
for gh in ROOM_GEOHASHES:
    for stype in ["jeonse", "monthly-rent", "rent", "oneroom"]:
        r = try_url(f"{BASE}/v3/items",
                    {"geohash": gh, "serviceType": stype},
                    label=f"geohash={gh} serviceType={stype}")
        if r and r.status_code == 200:
            body = r.json()
            lst = body.get("items", [])
            if lst:
                print(f"\n  ★★ 원룸 매물 발견! ({len(lst)}건) 첫 번째:")
                show_json(lst[0], 15)
                break
    else:
        continue
    break

print("\n  [참고] 원룸도 0건이면 → 인증 토큰 필요 확정")


# ─────────────────────────────────────────────────────────
sep("STEP 2. 인증 토큰 획득 시도")

# 직방 앱은 익명 OTP 토큰을 사용함
# 일반적인 흐름: POST /v1/auth/otpToken → JWT 획득 → Authorization 헤더 포함

AUTH_ENDPOINTS = [
    (f"{BASE}/v1/auth/otpToken",    "POST", {}),
    (f"{BASE}/v1/auth/token",       "POST", {}),
    (f"{BASE}/v1/auth/anonymous",   "POST", {"deviceId": "test-device-001"}),
    (f"{BASE}/v2/auth/token",       "POST", {}),
    (f"{BASE}/v1/token",            "POST", {}),
    (f"{BASE}/v1/auth",             "GET",  {}),
    (f"{BASE}/v2/token",            "GET",  {}),
]

token = None
for url, method, body in AUTH_ENDPOINTS:
    r = try_url(url, body, method=method, label=f"{method} {url.replace(BASE,'')}")
    if r and r.status_code == 200:
        try:
            data = r.json()
            print(f"  ★ 200 응답! 내용:")
            show_json(data, 15)
            # 토큰 추출 시도
            for key in ["token", "accessToken", "access_token", "jwt", "otp"]:
                if data.get(key):
                    token = data[key]
                    print(f"  → 토큰 발견: {key}={token[:30]}...")
                    break
        except Exception:
            print(f"  응답: {r.text[:200]}")

if not token:
    print("\n  → 모든 인증 엔드포인트 실패. 토큰 없이 계속 진행.")


# ─────────────────────────────────────────────────────────
sep("STEP 3. 토큰 포함하여 아파트 매물 재시도")

if token:
    auth_headers = {"Authorization": f"Bearer {token}"}
    test_params = [
        {"geohash": "wydm", "serviceType": "buy"},
        {"geohash": "wydmc", "serviceType": "buy"},
        {"areaId": "8192", "serviceType": "buy"},
    ]
    for p in test_params:
        try_url(f"{BASE}/v3/items", p, headers_extra=auth_headers,
                label=f"(with token) /v3/items {p}")
else:
    print("  토큰 없음 → 스킵")


# ─────────────────────────────────────────────────────────
sep("STEP 4. 대체 서브도메인 탐색")

ALT_BASES = [
    "https://oasis.zigbang.com",
    "https://api.zigbang.com",
    "https://apt.zigbang.com",
    "https://openapi.zigbang.com",
    "https://m.zigbang.com",
]

# 각 서브도메인에 대해 강남구 검색 + 아파트 조회 시도
for base in ALT_BASES:
    # 기본 접근
    r = try_url(base + "/", label=f"GET {base}/")
    if r and r.status_code not in [404, 0]:
        # 200이 아니더라도 응답이 있으면 더 탐색
        for path_params in [
            ("/v2/search",  {"q": "서울 강남구"}),
            ("/v3/items",   {"geohash": "wydm", "serviceType": "buy"}),
            ("/apt/items",  {"areaId": "8192"}),
        ]:
            path, params = path_params
            r2 = try_url(base + path, params, label=f"  {base}{path}")
            if r2 and r2.status_code == 200:
                try:
                    body = r2.json()
                    lst = (body.get("items") or body.get("list") or body.get("data")
                           if isinstance(body, dict) else body)
                    if lst:
                        print(f"  ★★ 매물 발견!")
                        show_json(lst[0] if isinstance(lst, list) else lst, 15)
                except Exception:
                    pass


# ─────────────────────────────────────────────────────────
sep("STEP 5. /v3/items 응답 헤더 상세 분석")

r = client.get(f"{BASE}/v3/items", params={"geohash": "wydm", "serviceType": "buy"})
print(f"  HTTP {r.status_code}")
print("\n  응답 헤더:")
for k, v in r.headers.items():
    if k.lower() in ["x-auth", "x-token", "www-authenticate", "x-request-id",
                     "set-cookie", "cache-control", "x-zigbang", "x-api-key",
                     "access-control-allow-origin", "content-type"]:
        print(f"    {k}: {v}")

print(f"\n  응답 바디 전체: {r.text}")


# ─────────────────────────────────────────────────────────
sep("STEP 6. 아파트 서비스 전용 경로 탐색")

# 직방 웹앱 /home/apt → 내부적으로 어떤 API를 쓰는지 추정
APT_PATHS = [
    "/apt/v1/items",
    "/apt/v2/items",
    "/home/apt/items",
    "/v2/apt/complexes",
    "/v3/apt/complexes",
    "/v4/items",
    "/v4/complexes",
    "/v2/items/complexes",
    "/v3/items/list",
]

for path in APT_PATHS:
    for params in [
        {},
        {"areaId": "8192"},
        {"complexId": "1626"},
        {"geohash": "wydm", "serviceType": "buy"},
    ]:
        r = try_url(f"{BASE}{path}", params, label=f"{path} {params if params else ''}")
        if r and r.status_code == 200:
            try:
                body = r.json()
                lst = (body.get("items") or body.get("list") or body.get("data")
                       if isinstance(body, dict) else body)
                if lst:
                    print(f"\n  ★★★ 매물 발견!")
                    show_json(lst[0] if isinstance(lst, list) else lst, 20)
            except Exception:
                print(f"  응답: {r.text[:100]}")
            break

sep("4차 진단 완료")
client.close()
