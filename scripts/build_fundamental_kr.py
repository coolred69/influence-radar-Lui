"""
KR 워치리스트 재무 펀더멘털 스코어링 — DART Open API 기반
Piotroski F-Score(9점) + Altman Z-Score 계산
US(FMP) 쪽 build_fundamental_table 로직과 대응되는 한국판.

DART는 FMP와 달리 사전계산된 스코어를 제공하지 않으므로,
재무상태표/손익계산서/현금흐름표 원자료(당기+전기)를 받아 직접 계산한다.

필요 환경변수: DART_API_KEY (.env)
"""
import json
import os
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

WATCHLIST_KR = [
    {"ticker": "005930", "name": "삼성전자"},
    {"ticker": "000660", "name": "SK하이닉스"},
    {"ticker": "005380", "name": "현대차"},
    {"ticker": "000270", "name": "기아"},
    {"ticker": "373220", "name": "LG에너지솔루션"},
    {"ticker": "035720", "name": "카카오"},
    {"ticker": "035420", "name": "네이버"},
    {"ticker": "096770", "name": "SK이노베이션"},
    {"ticker": "207940", "name": "삼성바이오로직스"},
    {"ticker": "051910", "name": "LG화학"},
]

ACCOUNT_IDS = {
    "assets": "ifrs-full_Assets",
    "liab": "ifrs-full_Liabilities",
    "ca": "ifrs-full_CurrentAssets",
    "cl": "ifrs-full_CurrentLiabilities",
    "revenue": "ifrs-full_Revenue",
    "ni": "ifrs-full_ProfitLoss",
    "cfo": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
    "opinc": "dart_OperatingIncomeLoss",
    "capital": "ifrs-full_IssuedCapital",
    "re": "ifrs-full_RetainedEarnings",
}


def load_corp_map():
    """corpCode.xml을 매번 3.6MB 다운로드하면 비효율적이므로 캐시 파일 사용.
    최초 1회 fetch_corp_code_map()으로 생성, 분기마다 갱신 권장."""
    cache = DATA_DIR / "dart_corp_map_kr.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"{cache} 없음 — fetch_corp_code_map.py 먼저 실행 필요"
    )


def fetch_financials(corp_code, bsns_year="2025", reprt_code="11011"):
    for fs_div in ("CFS", "OFS"):  # 연결 우선, 없으면 개별
        url = (
            f"https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
            f"?crtfc_key={DART_KEY}&corp_code={corp_code}"
            f"&bsns_year={bsns_year}&reprt_code={reprt_code}&fs_div={fs_div}"
        )
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "000":
            return data["list"], fs_div
    return [], None


def extract(rows):
    def num(x):
        try:
            return float(str(x).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0

    out = {}
    for key, aid in ACCOUNT_IDS.items():
        cur = prev = 0.0
        for r in rows:
            if r["account_id"] == aid:
                cur = num(r.get("thstrm_amount"))
                prev = num(r.get("frmtrm_amount"))
                break
        out[key] = {"cur": cur, "prev": prev}
    return out


def safe_div(a, b):
    return a / b if b else 0.0


def score(v, market_cap):
    """Piotroski F-Score(9) + Altman Z-Score 계산.
    8번 항목은 매출총이익률 대신 영업이익률 YoY 사용
    (네이버/카카오 등 플랫폼기업은 매출원가 계정이 XBRL에 없어 전종목 공통 지표로 통일)."""

    def g(key):
        return v[key]["cur"], v[key]["prev"]

    assets_c, assets_p = g("assets")
    liab_c, liab_p = g("liab")
    ca_c, ca_p = g("ca")
    cl_c, cl_p = g("cl")
    rev_c, rev_p = g("revenue")
    ni_c, ni_p = g("ni")
    cfo_c, _ = g("cfo")
    opinc_c, opinc_p = g("opinc")
    cap_c, cap_p = g("capital")
    re_c, _ = g("re")

    roa_c, roa_p = safe_div(ni_c, assets_c), safe_div(ni_p, assets_p)
    lev_c, lev_p = safe_div(liab_c, assets_c), safe_div(liab_p, assets_p)
    curr_c, curr_p = safe_div(ca_c, cl_c), safe_div(ca_p, cl_p)
    opm_c, opm_p = safe_div(opinc_c, rev_c), safe_div(opinc_p, rev_p)
    at_c, at_p = safe_div(rev_c, assets_c), safe_div(rev_p, assets_p)

    crit = {
        "ROA>0": roa_c > 0,
        "CFO>0": cfo_c > 0,
        "dROA>0": roa_c > roa_p,
        "CFO>NI": cfo_c > ni_c,
        "레버리지감소": lev_c < lev_p,
        "유동비율개선": curr_c > curr_p,
        "무증자": cap_c <= cap_p,
        "영업이익률개선": opm_c > opm_p,
        "자산회전율개선": at_c > at_p,
    }
    piotroski = sum(crit.values())

    mve = market_cap or 0
    A = safe_div(ca_c - cl_c, assets_c)
    B = safe_div(re_c, assets_c)
    C = safe_div(opinc_c, assets_c)
    D = safe_div(mve, liab_c)
    E = safe_div(rev_c, assets_c)
    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E

    return {
        "piotroski": piotroski,
        "piotroski_detail": crit,
        "altman_z": round(z, 2),
        "roa_pct": round(roa_c * 100, 2),
        "debt_ratio_pct": round(lev_c * 100, 1),
        "opm_pct": round(opm_c * 100, 2),
        "revenue_eok": round(rev_c / 1e8),
        "ni_eok": round(ni_c / 1e8),
        "market_cap_eok": round(mve / 1e8),
    }


def main():
    if not DART_KEY:
        raise SystemExit("DART_API_KEY 없음 — .env 확인 필요")

    import yfinance as yf

    corp_map = load_corp_map()
    results = []
    for item in WATCHLIST_KR:
        ticker = item["ticker"]
        info = corp_map.get(ticker)
        if not info:
            print(f"[SKIP] {ticker} corp_code 매핑 없음")
            continue
        rows, fs_div = fetch_financials(info["corp_code"])
        if not rows:
            print(f"[SKIP] {ticker} {item['name']} 재무데이터 조회 실패")
            continue
        v = extract(rows)
        try:
            mc = yf.Ticker(f"{ticker}.KS").fast_info.get("market_cap")
        except Exception:
            mc = None
        r = score(v, mc)
        r.update({"ticker": ticker, "name": item["name"], "fs_div": fs_div})
        results.append(r)

    results.sort(key=lambda x: (-x["piotroski"], -x["altman_z"]))

    out_path = DATA_DIR / "fundamental_kr.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장 완료: {out_path} ({len(results)}종목)")
    for r in results:
        zone = "안전" if r["altman_z"] > 2.99 else ("회색" if r["altman_z"] > 1.81 else "위험")
        print(f"{r['name']:10s} Piotroski={r['piotroski']}/9  Z={r['altman_z']:.2f}({zone})  ROA={r['roa_pct']}%")


if __name__ == "__main__":
    main()
