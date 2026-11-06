"""원본 xlsx(../data) → 대시보드용 data.js 생성.

원칙
- 원본 값은 변경하지 않는다(합산만 수행). 결측·이상값 후보도 삭제하지 않는다.
- 비짓제주 검색어: (기준년월, 분류명, 지역명, 주소) 동일 키에 최대 7행이 있으나
  구분 컬럼이 없어 의미를 알 수 없다 → 행을 삭제하지 않고 합산하며, 행 수를 함께 기록한다.
- 인기 장소: 장소 식별 = (목적지명, 목적지주소, 읍면동명, 카테고리 3단계) 원문 그대로.
  파일 용량 때문에 전체 기간 관광객 도착 수 합계가 PLACE_MIN 이상인 장소만 싣는다.
  (대시보드에서 순위 하한이 PLACE_MIN 미만이면 '생략 가능성' 경고를 띄운다.)

실행: python build_data.py   (pandas, openpyxl 필요)
"""
import json
import os
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data")
PLACE_MIN = 300


def read(name, **kw):
    return pd.read_excel(os.path.join(SRC, name + ".xlsx"), **kw)


def ym_list(start, end):
    out, y, m = [], start // 100, start % 100
    while y * 100 + m <= end:
        out.append(y * 100 + m)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def as_text(v):
    # 엑셀이 시간/날짜/숫자로 자동 변환한 이름도 문자열로만 바꿔 보존
    return str(v)


out = {"meta": {}, "checks": {}}

# 1) 연령대별 방문
a = read("제주 연령대별 방문")
out["age"] = a[["기준연월", "성별", "연령", "방문객수"]].values.tolist()
out["meta"]["age"] = {"rows": len(a), "min": int(a.기준연월.min()), "max": int(a.기준연월.max()),
                      "sex": sorted(a.성별.unique().tolist()), "ages": sorted(int(x) for x in a.연령.unique())}

# 2) 지역별 방문객(읍면동)
g = read("제주 지역별 방문객(읍면동)")
out["region"] = g[["기준연월", "시군구명", "읍면동명", "내국인 방문객수", "외국인 방문객수",
                   "총 방문객수 (내국인+외국인)"]].values.tolist()
out["regionAddr"] = read("제주 지역별 방문객(읍면동)", sheet_name="주민센터_주소목록").values.tolist()
emd = g[["시군구명", "읍면동명"]].drop_duplicates().sort_values(["시군구명", "읍면동명"])
out["emd"] = emd.values.tolist()
emd2sgg = dict(zip(emd.읍면동명, emd.시군구명))
out["meta"]["region"] = {"rows": len(g), "min": int(g.기준연월.min()), "max": int(g.기준연월.max())}

# 3) 월별 입도 관광객
m = read("월별 입도 관광객")
out["monthly"] = m.sort_values("기준연월").values.tolist()

# 4) 일별 입도 관광객 → 월 합계 대조용
d = read("입도 관광객 추이(일별)")
d["ym"] = d["기준일자(YYYYMMDD)"] // 100
dd = d.groupby("ym").agg(days=("전체방문객수", "size"), total=("전체방문객수", "sum")).reset_index()
out["dailyByMonth"] = dd.values.tolist()
out["meta"]["daily"] = {"rows": len(d), "min": int(d.iloc[:, 0].min()), "max": int(d.iloc[:, 0].max())}

# 5) 국가별 외국인 입도객 ('기타'는 월마다 2행 — 합치지 않고 행 그대로)
f = read("월간 국가별 외국인 입도객")
out["foreign"] = f.values.tolist()

# 6) 비짓제주 검색어
s = read("비짓제주 검색어 순위")
search_non_text = int(s["지역명"].map(lambda v: not isinstance(v, str)).sum())
s["지역명"] = s["지역명"].map(as_text)


def sgg_of(addr):
    t = str(addr).split()
    if len(t) > 1 and t[1] in ("제주시", "서귀포시"):
        return t[1]
    if len(t) > 1 and t[1] in emd2sgg:
        return emd2sgg[t[1]]
    return "미상"


sk = s.groupby(["기준년월", "분류명", "지역명", "주소"]).수치.agg(["sum", "size"]).reset_index()
ids = sk[["분류명", "지역명", "주소"]].drop_duplicates().reset_index(drop=True)
ids["sgg"] = ids.주소.map(sgg_of)
ids["i"] = ids.index
sk = sk.merge(ids, on=["분류명", "지역명", "주소"])
search_months = ym_list(int(s.기준년월.min()), int(s.기준년월.max()))
mi = {v: i for i, v in enumerate(search_months)}
cells = {}
for r in sk.itertuples(index=False):
    cells.setdefault(r.i, []).extend([mi[r.기준년월], int(r.sum)])
out["search"] = {
    "months": search_months,
    "ids": [[r.분류명, r.지역명, r.주소, r.sgg] for r in ids.itertuples(index=False)],
    "cells": [cells.get(i, []) for i in range(len(ids))],
}
out["meta"]["search"] = {"rows": len(s), "keys": len(sk), "min": int(s.기준년월.min()), "max": int(s.기준년월.max()),
                         "rowsPerKey": sk["size"].value_counts().sort_index().to_dict(),
                         "exactDupRows": int(s.duplicated().sum()), "nonTextNames": search_non_text}

# 7) 지역별 인기 장소
p = read("제주 지역별 인기 장소")
raw_names = p["목적지명"]
non_text = raw_names[raw_names.map(lambda v: not isinstance(v, str))]
p["목적지명"] = raw_names.map(as_text)
k = ["목적지명", "목적지주소", "읍면동명", "카테고리 3단계"]
pm = "주행일자(YYYYMM)"
tot = p.groupby(k)["관광객 도착 수"].sum()
keep = tot[tot >= PLACE_MIN].index
pk = p.set_index(k)
pk = pk[pk.index.isin(keep)].reset_index()
pk = pk.groupby(k + [pm])[["관광객 도착 수", "도민 도착 수", "도착건수"]].sum().reset_index()
place_months = ym_list(int(p[pm].min()), int(p[pm].max()))
pmi = {v: i for i, v in enumerate(place_months)}
pids = pk[k].drop_duplicates().reset_index(drop=True)
pids["i"] = pids.index
pk = pk.merge(pids, on=k)
pcells = {}
for r in pk.itertuples(index=False):
    pcells.setdefault(r.i, []).extend([pmi[r[4]], int(r[5]), int(r[6])])
cat_tot = p.groupby("카테고리 3단계")["관광객 도착 수"].sum().sort_values(ascending=False)
out["place"] = {
    "months": place_months,
    "min": PLACE_MIN,
    "ids": pids[k].values.tolist(),
    "cells": [pcells.get(i, []) for i in range(len(pids))],
    "cats": [[c, int(v)] for c, v in cat_tot.items()],
}
mt = p.groupby(pm).agg(tour=("관광객 도착 수", "sum"), res=("도민 도착 수", "sum"), arr=("도착건수", "sum"))
out["placeMonthTotal"] = mt.reset_index().values.tolist()
out["meta"]["place"] = {
    "rows": len(p), "min": int(p[pm].min()), "max": int(p[pm].max()),
    "identities": int(len(tot)), "kept": int(len(keep)),
    "keptShare": round(float(tot[tot >= PLACE_MIN].sum() / tot.sum() * 100), 1),
    "nonTextNames": non_text.map(lambda v: f"{type(v).__name__}:{v}").value_counts().to_dict(),
    "arrivalGapRows": int(((p["관광객 도착 수"] + p["도민 도착 수"]) != p["도착건수"]).sum()),
    "keyDupRows": int(p.duplicated(["주행일자(YYYYMM)", "목적지명", "목적지주소"]).sum()),
    "cats": int(p["카테고리 3단계"].nunique()),
}

# 8) 지도 경계 (읍면동 이름으로 결합, 43개 전부 일치 여부 기록)
geo = json.load(open(os.path.join(HERE, "source", "jeju_emd_2013.geojson"), encoding="utf-8"))
geo_names = {ft["properties"]["name"] for ft in geo["features"]}
out["geo"] = geo
out["checks"]["geoNameMatch"] = {"geoOnly": sorted(geo_names - set(emd2sgg)), "dataOnly": sorted(set(emd2sgg) - geo_names)}


def default(o):
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(type(o))


with open(os.path.join(HERE, "data.js"), "w", encoding="utf-8") as fp:
    fp.write("window.DASH_DATA=")
    json.dump(out, fp, ensure_ascii=False, separators=(",", ":"), default=default)
    fp.write(";\n")
print("data.js written", os.path.getsize(os.path.join(HERE, "data.js")) // 1024, "KB")
print(json.dumps(out["meta"], ensure_ascii=False, default=default, indent=1))
print(out["checks"])
