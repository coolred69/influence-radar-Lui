"""
Track C: 코스닥 소형주 리스크 스크리닝
설계: 2026-09-23, 재식님 지시 "다중설계" 트랙 C 우선 구축

목적: 소형주는 정보비대칭·조작·희석 리스크가 커서, 발굴보다 "부실 배제"가 핵심.
DART 공시(주요사항보고+거래소공시)를 매일 스캔해 위험 키워드가 뜬 종목을 걸러내고,
남은 종목만 펀더멘털 스코어로 순위를 매긴다.

효율성: 종목별로 재무제표/공시를 개별 조회하지 않고, DART list.json을 날짜범위+
corp_cls=K(코스닥) 조건으로 한 번에 긁어와서(페이지네이션) 우리 유니버스에 속한
종목만 매칭 — 800개 종목이어도 API 호출은 페이지 수만큼만 소요.

필요 환경변수: DART_API_KEY (.env)
필요 패키지: FinanceDataReader (KOSDAQ 종목 리스트+시가총액, KRX 로그인 불필요 —
             pykrx는 최신 버전에서 KRX_ID/KRX_PW 로그인을 요구해 배제)
"""
import json
import os
import datetime
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DART_KEY = os.environ.get("DART_API_KEY", "")
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# 소형주 정의: 코스닥, 시가총액 500억~3000억원, 거래정지 제외, 스팩/리츠/우선주 제외
MARKET_CAP_MIN = 50_000_000_000
MARKET_CAP_MAX = 300_000_000_000

# 공시 리스크 키워드 (report_nm 부분일치, [기재정정] 접두는 자동 무시)
RISK_KEYWORDS = {
    "CRITICAL": [
        "상장폐지", "관리종목", "거래정지", "파산신청", "회생절차개시신청",
        "감사의견거절", "감사의견한정", "해산사유발생", "자본잠식",
        "불성실공시법인지정", "투자유의안내",
    ],
    "HIGH": [
        "횡령", "배임", "유상증자결정", "전환사채권발행결정",
        "신주인수권부사채권발행결정", "교환사채권발행결정", "감자결정",
        "최대주주변경",
    ],
    "MEDIUM": [
        "타인을위한채무보증결정", "타인에대한채무보증결정", "금전대여결정",
        "소송등의판결", "영업양도결정", "영업양수결정",
    ],
    "POSITIVE": [
        "자기주식취득결정", "단일판매ㆍ공급계약체결",
    ],
}
RISK_SCORE = {"CRITICAL": -100, "HIGH": -25, "MEDIUM": -8, "POSITIVE": 5}


def get_smallcap_universe():
    """FinanceDataReader로 코스닥 소형주 유니버스 산출.
    pykrx는 최신 버전에서 KRX 로그인을 요구해서(KRX_ID/KRX_PW 미보유) 배제,
    FDR은 로그인 없이 동일 데이터(KRX 실시간 시세) 제공 확인됨."""
    import FinanceDataReader as fdr

    df = fdr.StockListing("KRX")
    kosdaq = df[df["Market"] == "KOSDAQ"].copy()
    kosdaq = kosdaq[~kosdaq["Name"].str.contains("스팩|리츠|우$", regex=True, na=False)]
    small = kosdaq[
        (kosdaq["Marcap"] >= MARKET_CAP_MIN)
        & (kosdaq["Marcap"] <= MARKET_CAP_MAX)
        & (kosdaq["Volume"] > 0)
    ]
    return {
        row["Code"]: {"name": row["Name"], "market_cap": int(row["Marcap"])}
        for _, row in small.iterrows()
    }


def fetch_recent_filings(days=14, pblntf_ty="B"):
    """최근 N일 공시 전체를 페이지네이션으로 수집 (corp_cls=K: 코스닥 한정)."""
    end = datetime.date.today().strftime("%Y%m%d")
    begin = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")
    all_rows = []
    page = 1
    while True:
        url = (
            f"https://opendart.fss.or.kr/api/list.json?crtfc_key={DART_KEY}"
            f"&bgn_de={begin}&end_de={end}&pblntf_ty={pblntf_ty}&corp_cls=K"
            f"&page_no={page}&page_count=100"
        )
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "000":
            break
        rows = data.get("list", [])
        all_rows.extend(rows)
        if page >= data.get("total_page", 1):
            break
        page += 1
    return all_rows


def classify_filing(report_nm):
    clean = report_nm.replace("[기재정정]", "").replace("[첨부정정]", "")
    # 거래정지 "해제"(정상화)는 위험 신호가 아니므로 제외
    if "거래정지" in clean and "해제" in clean:
        return None, clean
    for tier, keywords in RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in clean:
                return tier, clean
    return None, clean


def main():
    if not DART_KEY:
        raise SystemExit("DART_API_KEY 없음 — .env 확인 필요")

    universe = get_smallcap_universe()
    print(f"소형주 유니버스: {len(universe)}종목 (시총 500억~3000억, 코스닥)")

    filings_b = fetch_recent_filings(days=14, pblntf_ty="B")  # 주요사항보고
    filings_i = fetch_recent_filings(days=14, pblntf_ty="I")  # 거래소공시
    all_filings = filings_b + filings_i
    print(f"최근 14일 공시 수집: {len(all_filings)}건 (주요사항보고+거래소공시, 코스닥 전체)")

    flags = {}  # stock_code -> [(tier, clean_name, date), ...]
    for f in all_filings:
        code = f.get("stock_code", "").strip()
        if code not in universe:
            continue
        tier, clean = classify_filing(f["report_nm"])
        if tier is None:
            continue
        flags.setdefault(code, []).append(
            {"tier": tier, "report": clean, "date": f["rcept_dt"]}
        )

    results = []
    for code, info in universe.items():
        item_flags = flags.get(code, [])
        risk_score = sum(RISK_SCORE[f["tier"]] for f in item_flags)
        has_critical = any(f["tier"] == "CRITICAL" for f in item_flags)
        results.append({
            "ticker": code,
            "name": info["name"],
            "market_cap_eok": round(info["market_cap"] / 1e8),
            "risk_score": risk_score,
            "excluded": has_critical,
            "flags": item_flags,
        })

    results.sort(key=lambda x: (x["excluded"], x["risk_score"]))

    excluded = [r for r in results if r["excluded"]]
    flagged = [r for r in results if not r["excluded"] and r["risk_score"] < 0]
    clean = [r for r in results if not r["excluded"] and r["risk_score"] >= 0]

    print(f"\n[CRITICAL 배제] {len(excluded)}종목")
    for r in excluded[:20]:
        print(f"  {r['name']:12s} {[f['report'] for f in r['flags'] if f['tier']=='CRITICAL']}")

    print(f"\n[경고 플래그] {len(flagged)}종목 (risk_score<0)")
    for r in flagged[:10]:
        print(f"  {r['name']:12s} score={r['risk_score']}")

    print(f"\n[클린] {len(clean)}종목 (14일 내 위험공시 없음)")

    out_path = DATA_DIR / "smallcap_risk_screen.json"
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "universe_size": len(universe),
            "excluded_count": len(excluded),
            "flagged_count": len(flagged),
            "clean_count": len(clean),
            "results": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장 완료: {out_path}")


if __name__ == "__main__":
    main()
