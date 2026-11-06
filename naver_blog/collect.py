"""네이버 검색 API(블로그)로 제주 여행 후기 검색 결과를 수집한다.

2026-07-31부터 네이버 개발자센터의 검색 API 신규 신청이 중단되고 NAVER API HUB(네이버 클라우드)로 이관됨.
- 기본(hub): https://naverapihub.apigw.ntruss.com/search/v1/blog, 헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY
- 2026-07-25 이전에 개발자센터 키를 받은 경우: NAVER_API=legacy 로 실행(발급 후 1년간 사용 가능)

- 수집 항목: 제목, 요약문(description), 게시일(postdate), 링크, 블로거명 — API가 주는 값 그대로
- 본문 전체는 수집하지 않는다(API 미제공, 크롤링은 이용약관 위반 소지).
- 결과는 원본 응답 그대로 raw/ 에 JSON Lines로 저장(수집 시각·검색어·정렬·순위 포함).

실행
  export NAVER_CLIENT_ID=발급받은ID          # API HUB의 Client ID
  export NAVER_CLIENT_SECRET=발급받은Secret  # API HUB의 Client Secret
  python collect.py                 # queries.txt 의 검색어 전부
  python collect.py "제주 20대 여행"  # 특정 검색어만
"""
import datetime as dt
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENDPOINTS = {
    "hub": ("https://naverapihub.apigw.ntruss.com/search/v1/blog", "X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
    "legacy": ("https://openapi.naver.com/v1/search/blog.json", "X-Naver-Client-Id", "X-Naver-Client-Secret"),
}
MODE = os.environ.get("NAVER_API", "hub")
API, HDR_ID, HDR_SECRET = ENDPOINTS[MODE]
DISPLAY = 100          # 한 번에 최대 100건
MAX_START = 1000       # API가 허용하는 start 최댓값 → 검색어당 최대 1,000건
SORT = "sim"           # sim(정확도순) / date(최신순)

try:  # python.org 설치판 macOS Python은 인증서가 없어 SSL 오류가 나므로 certifi가 있으면 사용
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()
SSL_HINT = ("SSL 인증서 확인 실패: macOS라면 Finder > 응용 프로그램 > Python 3.x 폴더의 "
            "'Install Certificates.command'를 실행하거나 'pip install certifi' 후 다시 실행하세요.")


def load_queries():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    with open(os.path.join(HERE, "queries.txt"), encoding="utf-8") as f:
        return [q.strip() for q in f if q.strip() and not q.startswith("#")]


def call(query, start, cid, secret):
    url = API + "?" + urllib.parse.urlencode({"query": query, "display": DISPLAY, "start": start, "sort": SORT})
    req = urllib.request.Request(url, headers={HDR_ID: cid, HDR_SECRET: secret})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        return json.load(r)


def collect_all(out, stamp, cid, secret):
    rows = 0
    for q in load_queries():
        got, total = 0, None
        for start in range(1, MAX_START + 1, DISPLAY):
            try:
                res = call(q, start, cid, secret)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                print(f"[{q}] start={start} HTTP {e.code}: {body}")
                if e.code in (401, 403):
                    sys.exit(f"인증 실패({MODE}): Client ID/Secret, Application에 '블로그 검색' API 선택 여부, "
                             "NAVER_API 설정(hub/legacy)이 키 발급처와 맞는지 확인하세요.")
                if e.code == 429:
                    sys.exit("호출 한도 초과(429): 잠시 후 다시 실행하거나 월 한도를 확인하세요.")
                break
            except urllib.error.URLError as e:
                if isinstance(e.reason, ssl.SSLError):
                    sys.exit(SSL_HINT)
                print(f"[{q}] start={start} 연결 오류: {e.reason}")
                break
            total = res.get("total")
            items = res.get("items", [])
            for rank, it in enumerate(items, start=start):
                out.write(json.dumps({"collected_at": stamp, "query": q, "sort": SORT, "rank": rank,
                                      "api_total": total, **it}, ensure_ascii=False) + "\n")
            got += len(items)
            if len(items) < DISPLAY:
                break
            time.sleep(0.15)
        rows += got
        print(f"[{q}] 검색 결과 총 {total}건 중 {got}건 수집 ({MODE})")
    return rows


def main():
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수를 설정하세요 (README 참고).")
    os.makedirs(os.path.join(HERE, "raw"), exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(HERE, "raw", f"blog_{stamp}.jsonl")
    rows = 0
    try:
        with open(out_path, "w", encoding="utf-8") as out:
            rows = collect_all(out, stamp, cid, secret)
    finally:
        if rows == 0 and os.path.exists(out_path):
            os.remove(out_path)  # 빈 파일은 남기지 않음
    print("저장:", out_path if rows else "(수집된 행 없음)")


if __name__ == "__main__":
    main()
