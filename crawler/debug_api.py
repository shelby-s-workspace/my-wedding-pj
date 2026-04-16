"""
네이버 부동산 API 연결 진단 스크립트

실행: py debug_api.py
"""
import socket
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://fin.land.naver.com/",
}

TARGETS = [
    "new.land.naver.com",
    "fin.land.naver.com",
]

API_PARAMS = {
    "cortarNo":       "1168000000",  # 강남구
    "order":          "rank",
    "realEstateType": "APT",
    "tradeType":      "A1",
    "priceMin":       60000,
    "priceMax":       100000,
    "areaMin":        49,
    "page":           1,
    "pageSize":       3,
}


def sep(title=""):
    print(f"\n{'='*55}")
    if title:
        print(f"  {title}")
        print(f"{'='*55}")


def check_dns(host):
    try:
        ip = socket.gethostbyname(host)
        print(f"  DNS ✓  {host} → {ip}")
        return True
    except socket.gaierror as e:
        print(f"  DNS ✗  {host} → 해석 실패: {e}")
        return False


def check_url(base_url, timeout=10):
    sep(f"테스트: {base_url}")

    host = base_url.replace("https://", "").replace("http://", "").split("/")[0]

    # 1. DNS
    if not check_dns(host):
        print("  → DNS 해석 실패. 네트워크 또는 방화벽 문제.")
        return

    # 2. 메인 페이지
    try:
        r = httpx.get(base_url + "/", headers=HEADERS, timeout=timeout, follow_redirects=True)
        print(f"  메인  ✓  HTTP {r.status_code}  (최종 URL: {r.url})")
    except httpx.TimeoutException:
        print(f"  메인  ✗  Timeout ({timeout}s) — 서버가 응답 안 함 (차단 가능성)")
        return
    except Exception as e:
        print(f"  메인  ✗  오류: {e}")
        return

    # 3. API 엔드포인트
    api_url = f"{base_url}/api/articles"
    try:
        r2 = httpx.get(api_url, params=API_PARAMS, headers=HEADERS,
                       timeout=timeout, follow_redirects=True)
        print(f"  API   ✓  HTTP {r2.status_code}")
        body = r2.text[:400]
        print(f"  응답 미리보기:\n{body}\n{'─'*40}")
    except httpx.TimeoutException:
        print(f"  API   ✗  Timeout ({timeout}s) — 인증 없이 차단됨 → auth.yaml 설정 필요")
    except Exception as e:
        print(f"  API   ✗  오류: {e}")


# ──────────────────────────────────────────
sep("네이버 부동산 API 연결 진단")
for base in TARGETS:
    check_url(f"https://{base}")

sep("진단 완료")
print("""
[결과 해석]
  DNS ✗        → 네트워크/방화벽에서 도메인 차단
  메인 ✗ timeout → 서버가 요청 자체를 차단 (IP 차단 또는 방화벽)
  메인 ✓ / API ✗ → 인증 없이 API 차단 → auth.yaml 쿠키 설정으로 해결
  API ✓         → 정상 연결! py main.py 실행 가능
""")
