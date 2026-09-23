"""
Track A: 미국 대형주 펀더멘털 스코어 (FMP API 기반)
설계: 2026-09-23, KR(DART) 버전과 동일한 방법론을 미국 8종목에 적용

산출: Piotroski F-Score(9점), Altman Z-Score, 애널리스트 목표주가 업사이드%,
      fundamental_score = 0.4*(Piotroski/9*100) + 0.3*(clip(AltmanZ,0,10)/10*100)
                          + 0.3*(clip(업사이드%,-20,50) 정규화)
      (combined_probability_table.json에 기록된 기존 수동 계산 방법론과 동일 — 검증됨)

필요 환경변수: FMP_API_KEY (.env 또는 GitHub Actions Secret)
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

FMP_KEY = os.environ.get("FMP_API_KEY", "")
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

WATCHLIST_US = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]


def get(path):
    sep = "&" if "?" in path else "?"
    url = f"https://financialmodelingprep.com/stable/{path}{sep}apikey={FMP_KEY}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode())


def safe_div(a, b):
    return a / b if b else 0.0


def score_piotroski(cur, prev):
    roa_cur = safe_div(cur["netIncome"], cur["totalAssets"])
    roa_prev = safe_div(prev["netIncome"], prev["totalAssets"])
    lev_cur = safe_div(cur["longTermDebt"], cur["totalAssets"])
    lev_prev = safe_div(prev["longTermDebt"], prev["totalAssets"])
    cr_cur = safe_div(cur["totalCurrentAssets"], cur["totalCurrentLiabilities"])
    cr_prev = safe_div(prev["totalCurrentAssets"], prev["totalCurrentLiabilities"])
    gm_cur = safe_div(cur["grossProfit"], cur["revenue"])
    gm_prev = safe_div(prev["grossProfit"], prev["revenue"])
    at_cur = safe_div(cur["revenue"], cur["totalAssets"])
    at_prev = safe_div(prev["revenue"], prev["totalAssets"])

    detail = {
        "roa_positive": roa_cur > 0,
        "cfo_positive": cur["operatingCashFlow"] > 0,
        "roa_improved": roa_cur > roa_prev,
        "cfo_over_ni": cur["operatingCashFlow"] > cur["netIncome"],
        "leverage_decreased": lev_cur < lev_prev,
        "liquidity_improved": cr_cur > cr_prev,
        "no_new_shares": cur["commonStockIssuance"] <= 0,
        "gross_margin_improved": gm_cur > gm_prev,
        "asset_turnover_improved": at_cur > at_prev,
    }
    return sum(detail.values()), detail, roa_cur


def score_altman_z(cur, market_cap):
    wc = cur["totalCurrentAssets"] - cur["totalCurrentLiabilities"]
    A = safe_div(wc, cur["totalAssets"])
    B = safe_div(cur["retainedEarnings"], cur["totalAssets"])
    C = safe_div(cur["ebit"], cur["totalAssets"])
    D = safe_div(market_cap, cur["totalLiabilities"])
    E = safe_div(cur["revenue"], cur["totalAssets"])
    return round(1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E, 2)


def fundamental_score(piotroski, altman_z, upside_pct):
    p_part = 0.4 * (piotroski / 9 * 100)
    z_clip = max(0, min(altman_z, 10))
    z_part = 0.3 * (z_clip / 10 * 100)
    u_clip = max(-20, min(upside_pct, 50))
    u_part = 0.3 * ((u_clip + 20) / 70 * 100)
    return round(p_part + z_part + u_part, 1)


def main():
    if not FMP_KEY:
        raise SystemExit("FMP_API_KEY 없음 — .env 또는 Secret 확인 필요")

    results = []
    for ticker in WATCHLIST_US:
        inc = get(f"income-statement?symbol={ticker}&limit=2")
        bs = get(f"balance-sheet-statement?symbol={ticker}&limit=2")
        cf = get(f"cash-flow-statement?symbol={ticker}&limit=2")
        pt = get(f"price-target-consensus?symbol={ticker}")
        q = get(f"quote?symbol={ticker}")

        cur = {**inc[0], **bs[0], **cf[0]}
        prev = {**inc[1], **bs[1], **cf[1]}
        price = q[0]["price"] if isinstance(q, list) else q["price"]
        market_cap = q[0]["marketCap"] if isinstance(q, list) else q["marketCap"]
        target = pt[0]["targetConsensus"] if pt else None
        upside_pct = round((target - price) / price * 100, 1) if target else None

        piotroski, detail, roa = score_piotroski(cur, prev)
        altman_z = score_altman_z(cur, market_cap)
        fscore = fundamental_score(piotroski, altman_z, upside_pct if upside_pct is not None else 0)

        results.append({
            "ticker": ticker,
            "name": q[0].get("name") if isinstance(q, list) else q.get("name"),
            "piotroski": piotroski,
            "piotroski_detail": detail,
            "altman_z": altman_z,
            "upside_pct": upside_pct,
            "roa_pct": round(roa * 100, 2),
            "market_cap_usd": market_cap,
            "fundamental_score": fscore,
        })
        print(f"{ticker:6s} Piotroski={piotroski}/9  AltmanZ={altman_z}  Upside={upside_pct}%  Fund={fscore}")

    results.sort(key=lambda x: x["fundamental_score"], reverse=True)

    out_path = DATA_DIR / "fundamental_us.json"
    out_path.write_text(
        json.dumps({
            "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "methodology": "fundamental_score = 0.4*(Piotroski/9*100) + 0.3*(clip(AltmanZ,0,10)/10*100) + 0.3*(clip(upside%,-20,50) 정규화)",
            "results": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장 완료: {out_path}")


if __name__ == "__main__":
    main()
