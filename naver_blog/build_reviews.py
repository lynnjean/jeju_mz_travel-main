"""raw/*.jsonl(네이버 블로그 검색 결과) → ../reviews.js (대시보드 9번 영역용).

- HTML 태그(<b>)와 엔티티만 정리하고 문장은 바꾸지 않는다.
- 같은 링크가 여러 검색어·수집 회차에 나오면 1건으로 합치고, 걸린 검색어 목록을 남긴다.
  (원본 raw 파일은 그대로 둔다.)
- topics.json 키워드가 제목+요약문에 있으면 해당 주제 '언급'으로 태그한다(감성 분석 아님).
- 광고성 키워드가 제목·요약문에 있으면 ad=1. 요약문에 없는 광고 표기는 잡지 못한다.
- '_20대 관련 표시' 단어가 있으면 y=1. 검색어의 '20대'가 '20개월'처럼 분리 매칭되는 글을 구분하기 위함.

실행: python build_reviews.py
"""
import glob
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = re.compile(r"<[^>]+>")


def clean(s):
    return html.unescape(TAG.sub("", s or "")).strip()


def main():
    files = sorted(glob.glob(os.path.join(HERE, "raw", "*.jsonl")))
    if not files:
        raise SystemExit("raw/ 에 수집 파일이 없습니다. 먼저 collect.py 를 실행하세요.")
    topics = json.load(open(os.path.join(HERE, "topics.json"), encoding="utf-8"))
    ad_words = topics["_광고성 표시"]
    youth_words = topics.get("_20대 관련 표시", [])
    jeju_words = topics.get("_제주 관련 표시", [])
    groups = {g: v for g, v in topics.items() if not g.startswith("_")}

    posts, runs, raw_rows = {}, {}, 0
    for fp in files:
        for line in open(fp, encoding="utf-8"):
            r = json.loads(line)
            raw_rows += 1
            key = (r["collected_at"], r["query"])
            run = runs.setdefault(key, {"collected_at": r["collected_at"], "query": r["query"], "sort": r["sort"],
                                        "api_total": r.get("api_total"), "fetched": 0})
            run["fetched"] += 1
            p = posts.get(r["link"])
            if p is None:
                title, desc = clean(r.get("title")), clean(r.get("description"))
                text = title + " " + desc
                tags = [f"{g}|{t}" for g, ts in groups.items() for t, kws in ts.items() if any(k in text for k in kws)]
                p = posts[r["link"]] = {"t": title, "d": desc, "link": r["link"], "date": r.get("postdate", ""),
                                        "blogger": clean(r.get("bloggername")), "q": [],
                                        "tags": tags, "ad": int(any(k in text for k in ad_words)),
                                        "y": int(any(k in text for k in youth_words)),
                                        "j": int(any(k in text for k in jeju_words))}
            if r["query"] not in p["q"]:
                p["q"].append(r["query"])

    out = {
        "meta": {"files": [os.path.basename(f) for f in files], "rawRows": raw_rows, "unique": len(posts),
                 "runs": sorted(runs.values(), key=lambda x: (x["collected_at"], x["query"])),
                 "groups": {g: {t: kws for t, kws in ts.items()} for g, ts in groups.items()}, "adWords": ad_words,
                 "youthWords": youth_words},
        "posts": sorted(posts.values(), key=lambda p: p["date"], reverse=True),
    }
    dst = os.path.join(HERE, "..", "reviews.js")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("window.REVIEW_DATA=")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"원본 {raw_rows}행 → 고유 게시글 {len(posts)}건, 광고성 표시 {sum(p['ad'] for p in posts.values())}건, "
          f"20대 관련 단어 포함 {sum(p['y'] for p in posts.values())}건")
    print("저장:", os.path.normpath(dst))


if __name__ == "__main__":
    main()
