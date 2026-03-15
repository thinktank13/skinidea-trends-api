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
from typing import List, Optional
from datetime import datetime, timedelta

app = FastAPI(title="스킨이데아 트렌드 API", version="1.0.0")

# CORS 설정 (프론트엔드에서 호출 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 권역 → Google Trends geo 코드 매핑 ───
REGION_GEO = {
    "global":          "",
    "north_america":   "",       # 국가 개별 지정
    "central_america": "",
    "south_america":   "",
    "russia":          "RU",
    "cis":             "",
    "europe":          "",
    "middle_east":     "",
    "southeast_asia":  "",
    "japan":           "JP",
    "china":           "CN",
}

# 권역별 대표 국가 geo 코드 (글로벌 집계용 - 단일 geo 사용)
REGION_REPRESENTATIVE_GEO = {
    "north_america":   "US",
    "central_america": "MX",
    "south_america":   "BR",
    "cis":             "KZ",
    "europe":          "DE",
    "middle_east":     "SA",
    "southeast_asia":  "ID",
}

# 국가 이름 → geo 코드
COUNTRY_GEO = {
    "미국": "US", "캐나다": "CA", "멕시코": "MX",
    "과테말라": "GT", "코스타리카": "CR", "파나마": "PA", "쿠바": "CU", "도미니카": "DO",
    "브라질": "BR", "아르헨티나": "AR", "콜롬비아": "CO", "칠레": "CL", "페루": "PE", "에콰도르": "EC",
    "러시아": "RU",
    "우크라이나": "UA", "카자흐스탄": "KZ", "우즈베키스탄": "UZ", "벨라루스": "BY", "아제르바이잔": "AZ", "조지아": "GE",
    "독일": "DE", "프랑스": "FR", "영국": "GB", "이탈리아": "IT", "스페인": "ES",
    "폴란드": "PL", "네덜란드": "NL", "스웨덴": "SE", "스위스": "CH",
    "사우디아라비아": "SA", "UAE": "AE", "이란": "IR", "이스라엘": "IL",
    "터키": "TR", "이집트": "EG", "쿠웨이트": "KW",
    "인도네시아": "ID", "베트남": "VN", "태국": "TH", "필리핀": "PH",
    "말레이시아": "MY", "싱가포르": "SG", "미얀마": "MM",
    "일본": "JP", "중국": "CN",
}

def get_geo(region: str, country: Optional[str]) -> str:
    """권역/국가에서 geo 코드 결정"""
    if country and country in COUNTRY_GEO:
        return COUNTRY_GEO[country]
    direct = REGION_GEO.get(region, "")
    if direct:
        return direct
    return REGION_REPRESENTATIVE_GEO.get(region, "")

def safe_trends_request(keywords: List[str], timeframe: str, geo: str, retries: int = 3):
    """
    pytrends 요청 (rate limit 대응 재시도 포함)
    Google Trends는 비공식 API이므로 요청 간격 필수
    """
    for attempt in range(retries):
        try:
            # hl: 언어, tz: 시간대(540=KST)
            pt = TrendReq(hl='ko-KR', tz=540, timeout=(10, 30), retries=2, backoff_factor=0.5)
            pt.build_payload(
                kw_list=keywords[:5],  # Google Trends 최대 5개
                timeframe=timeframe,
                geo=geo,
                gprop=''
            )
            df = pt.interest_over_time()
            if df.empty:
                return None
            # isPartial 컬럼 제거
            if 'isPartial' in df.columns:
                df = df.drop(columns=['isPartial'])
            return df
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 2 + random.uniform(0, 1)
                time.sleep(wait)
            else:
                raise HTTPException(status_code=503, detail=f"Google Trends 요청 실패: {str(e)}")

def build_timeframe(date_from: str, date_to: str) -> str:
    """날짜 문자열 → pytrends timeframe 형식"""
    return f"{date_from} {date_to}"

@app.get("/")
def root():
    return {"status": "ok", "service": "스킨이데아 트렌드 API", "version": "1.0.0"}

@app.get("/api/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/trends")
def get_trends(
    keywords: str = Query(..., description="쉼표 구분 키워드 (최대 5개). 예: niacinamide,ceramide,retinol"),
    date_from: str = Query("2024-01-01", description="시작일 YYYY-MM-DD"),
    date_to:   str = Query("2025-01-01", description="종료일 YYYY-MM-DD"),
    region:    str = Query("global",     description="권역 코드"),
    country:   str = Query("",           description="세부 국가명 (한국어). 예: 미국"),
    granularity: str = Query("monthly",  description="monthly | weekly | yearly"),
):
    """
    검색 트렌드 시계열 데이터 반환
    
    반환 형식:
    {
      "labels": ["2024-01", "2024-02", ...],
      "datasets": [
        {"keyword": "niacinamide", "data": [45, 52, 60, ...]},
        ...
      ],
      "source": "Google Trends",
      "geo": "US",
      "region_label": "북미"
    }
    """
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()][:5]
    if not kw_list:
        raise HTTPException(status_code=400, detail="keywords 파라미터가 필요합니다")

    geo = get_geo(region, country if country else None)
    timeframe = build_timeframe(date_from, date_to)

    # Google Trends 요청
    df = safe_trends_request(kw_list, timeframe, geo)

    if df is None or df.empty:
        return {
            "labels": [],
            "datasets": [{"keyword": k, "data": []} for k in kw_list],
            "source": get_source_label(region),
            "geo": geo,
            "region_label": get_region_label(region),
            "note": "해당 기간/지역 데이터 없음"
        }

    # 월별/주별/연별 리샘플링
    if granularity == "monthly":
        df = df.resample('MS').mean().round(1)
    elif granularity == "yearly":
        df = df.resample('YS').mean().round(1)
    # weekly는 기본값 그대로

    labels = [idx.strftime("%Y-%m") if granularity != "yearly" else str(idx.year)
              for idx in df.index]

    datasets = []
    for kw in kw_list:
        col = kw if kw in df.columns else None
        if col:
            data = [round(float(v), 1) if not __import__('math').isnan(v) else 0
                    for v in df[col].tolist()]
        else:
            data = [0] * len(labels)
        datasets.append({"keyword": kw, "data": data})

    return {
        "labels": labels,
        "datasets": datasets,
        "source": get_source_label(region),
        "geo": geo,
        "region_label": get_region_label(region),
    }

@app.get("/api/trends/compare")
def compare_trends(
    keywords: str = Query(..., description="쉼표 구분 키워드"),
    date_from: str = Query("2024-01-01"),
    date_to:   str = Query("2025-01-01"),
    region:    str = Query("global"),
    country:   str = Query(""),
):
    """
    키워드 5개 초과 시 배치 처리 (5개씩 나눠 요청 후 합산)
    """
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        raise HTTPException(status_code=400, detail="keywords 필요")

    geo = get_geo(region, country if country else None)
    timeframe = build_timeframe(date_from, date_to)

    all_datasets = {}
    all_labels = []

    # 5개씩 배치
    for i in range(0, len(kw_list), 5):
        batch = kw_list[i:i+5]
        time.sleep(1.5)  # rate limit 방지
        df = safe_trends_request(batch, timeframe, geo)
        if df is None:
            continue
        df_m = df.resample('MS').mean().round(1)
        if not all_labels:
            all_labels = [idx.strftime("%Y-%m") for idx in df_m.index]
        for kw in batch:
            if kw in df_m.columns:
                all_datasets[kw] = [round(float(v), 1) for v in df_m[kw].tolist()]

    datasets = [{"keyword": k, "data": all_datasets.get(k, [0]*len(all_labels))} for k in kw_list]

    return {
        "labels": all_labels,
        "datasets": datasets,
        "source": get_source_label(region),
        "geo": geo,
        "region_label": get_region_label(region),
    }

@app.get("/api/regions")
def get_regions():
    """권역 목록 및 메타데이터"""
    return {
        "regions": [
            {"id": k, "label": get_region_label(k), "source": get_source_label(k),
             "geo": REGION_GEO.get(k, "") or REGION_REPRESENTATIVE_GEO.get(k, "")}
            for k in REGION_GEO
        ]
    }

def get_source_label(region: str) -> str:
    if region == "japan":  return "Yahoo Japan Trends (Google JP)"
    if region == "china":  return "Google Trends (CN)"
    return "Google Trends"

def get_region_label(region: str) -> str:
    labels = {
        "global": "글로벌 전체", "north_america": "북미", "central_america": "중미",
        "south_america": "남미", "russia": "러시아", "cis": "러시아 제외 CIS",
        "europe": "유럽", "middle_east": "중동", "southeast_asia": "동남아",
        "japan": "일본", "china": "중국",
    }
    return labels.get(region, region)
