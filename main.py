"""
스킨이데아 글로벌 검색 트렌드 API
- Google Trends (pytrends) 기반
- 일본: geo=JP, 중국: geo=CN 지역 필터
- 전 권역 지원
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pytrends.request import TrendReq
import time
import random
import requests
import math
from requests.adapters import HTTPAdapter
from typing import Optional
from datetime import datetime

app = FastAPI(title="스킨이데아 트렌드 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REGION_GEO = {
    "global":"","north_america":"US","central_america":"MX",
    "south_america":"BR","russia":"RU","cis":"KZ",
    "europe":"DE","middle_east":"SA","southeast_asia":"ID",
    "japan":"JP","china":"CN",
}

COUNTRY_GEO = {
    "미국":"US","캐나다":"CA","멕시코":"MX","과테말라":"GT","코스타리카":"CR",
    "파나마":"PA","쿠바":"CU","도미니카":"DO","브라질":"BR","아르헨티나":"AR",
    "콜롬비아":"CO","칠레":"CL","페루":"PE","에콰도르":"EC","러시아":"RU",
    "우크라이나":"UA","카자흐스탄":"KZ","우즈베키스탄":"UZ","벨라루스":"BY",
    "아제르바이잔":"AZ","조지아":"GE","독일":"DE","프랑스":"FR","영국":"GB",
    "이탈리아":"IT","스페인":"ES","폴란드":"PL","네덜란드":"NL","스웨덴":"SE",
    "스위스":"CH","사우디아라비아":"SA","UAE":"AE","이란":"IR","이스라엘":"IL",
    "터키":"TR","이집트":"EG","쿠웨이트":"KW","인도네시아":"ID","베트남":"VN",
    "태국":"TH","필리핀":"PH","말레이시아":"MY","싱가포르":"SG","미얀마":"MM",
    "일본":"JP","중국":"CN",
}

def get_geo(region: str, country: Optional[str]) -> str:
    if country and country in COUNTRY_GEO:
        return COUNTRY_GEO[country]
    return REGION_GEO.get(region, "")

def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://trends.google.com/",
    })
    session.mount("https://", HTTPAdapter(max_retries=2))
    return session

def safe_trends_request(keywords: list, timeframe: str, geo: str, retries: int = 3):
    last_error = None
    for attempt in range(retries):
        try:
            if attempt > 0:
                time.sleep(attempt * 3 + random.uniform(1, 3))
            session = build_session()
            pt = TrendReq(
                hl="en-US", tz=0, timeout=(15, 40),
                requests_args={"verify": True, "headers": session.headers},
                retries=1, backoff_factor=1.0,
            )
            pt.build_payload(kw_list=keywords[:5], timeframe=timeframe, geo=geo, gprop="")
            df = pt.interest_over_time()
            if df is not None and not df.empty:
                if "isPartial" in df.columns:
                    df = df.drop(columns=["isPartial"])
                return df
        except Exception as e:
            last_error = str(e)
            continue
    raise HTTPException(status_code=503, detail=f"Google Trends 요청 실패 ({retries}회 재시도): {last_error}")

def resample_df(df, granularity):
    if granularity == "monthly":
        return df.resample("MS").mean().round(1)
    elif granularity == "yearly":
        return df.resample("YS").mean().round(1)
    return df

def df_to_labels(df, granularity):
    return [idx.strftime("%Y-%m") if granularity != "yearly" else str(idx.year) for idx in df.index]

def safe_val(v):
    return 0 if math.isnan(v) else round(float(v), 1)

def get_source_label(region):
    if region == "japan": return "Google Trends (JP)"
    if region == "china": return "Google Trends (CN)"
    return "Google Trends"

def get_region_label(region):
    return {
        "global":"글로벌 전체","north_america":"북미","central_america":"중미",
        "south_america":"남미","russia":"러시아","cis":"러시아 제외 CIS",
        "europe":"유럽","middle_east":"중동","southeast_asia":"동남아",
        "japan":"일본","china":"중국",
    }.get(region, region)

@app.get("/")
def root():
    return {"status":"ok","service":"스킨이데아 트렌드 API","version":"1.0.0"}

@app.get("/api/health")
def health():
    return {"status":"healthy","timestamp":datetime.now().isoformat()}

@app.get("/api/trends")
def get_trends(
    keywords:    str = Query(...),
    date_from:   str = Query("2024-01-01"),
    date_to:     str = Query("2025-01-01"),
    region:      str = Query("global"),
    country:     str = Query(""),
    granularity: str = Query("monthly"),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:5]
    if not kw_list:
        raise HTTPException(status_code=400, detail="keywords 파라미터가 필요합니다")

    geo = get_geo(region, country if country else None)
    timeframe = f"{date_from} {date_to}"
    time.sleep(random.uniform(0.5, 1.5))

    df = safe_trends_request(kw_list, timeframe, geo)

    if df is None or df.empty:
        return {"labels":[],"datasets":[{"keyword":k,"data":[]} for k in kw_list],
                "source":get_source_label(region),"geo":geo,
                "region_label":get_region_label(region),"note":"데이터 없음"}

    df = resample_df(df, granularity)
    labels = df_to_labels(df, granularity)
    datasets = [
        {"keyword":kw,"data":[safe_val(v) for v in df[kw].tolist()] if kw in df.columns else [0]*len(labels)}
        for kw in kw_list
    ]

    return {"labels":labels,"datasets":datasets,
            "source":get_source_label(region),"geo":geo,
            "region_label":get_region_label(region)}

@app.get("/api/trends/compare")
def compare_trends(
    keywords:    str = Query(...),
    date_from:   str = Query("2024-01-01"),
    date_to:     str = Query("2025-01-01"),
    region:      str = Query("global"),
    country:     str = Query(""),
    granularity: str = Query("monthly"),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        raise HTTPException(status_code=400, detail="keywords 필요")

    geo = get_geo(region, country if country else None)
    timeframe = f"{date_from} {date_to}"
    all_datasets: dict = {}
    all_labels: list = []

    for i in range(0, len(kw_list), 5):
        batch = kw_list[i:i+5]
        time.sleep(random.uniform(2.0, 4.0))
        try:
            df = safe_trends_request(batch, timeframe, geo)
            if df is None or df.empty:
                continue
            df = resample_df(df, granularity)
            if not all_labels:
                all_labels = df_to_labels(df, granularity)
            for kw in batch:
                if kw in df.columns:
                    all_datasets[kw] = [safe_val(v) for v in df[kw].tolist()]
        except Exception:
            continue

    datasets = [{"keyword":k,"data":all_datasets.get(k,[0]*len(all_labels))} for k in kw_list]
    return {"labels":all_labels,"datasets":datasets,
            "source":get_source_label(region),"geo":geo,
            "region_label":get_region_label(region)}

@app.get("/api/regions")
def get_regions():
    return {"regions":[
        {"id":k,"label":get_region_label(k),"source":get_source_label(k),"geo":v}
        for k,v in REGION_GEO.items()
    ]}
