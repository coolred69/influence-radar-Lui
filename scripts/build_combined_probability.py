"""
US+KR 통합 종합확률 테이블 자동 생성
설계: 2026-09-23 수동 1회 생성분을 완전 자동화

입력:
  - data/fundamental_us.json (build_fundamental_us.py, FMP 기반)
  - data/fundamental_kr.json (build_fundamental_kr.py, DART 기반)
  - data/signals.json (signal_engine.py, 매일 자동 갱신 — 보정 기술점수 'score' 필드 사용,
    KR 종목은 symbol이 "005930.KS" 형태라 ".KS" 접미사를 떼고 매칭)

산출: data/combined_probability_table.json
  final_score = 0.5*fundamental_score + 0.5*tech_score(보정)
  US: fundamental_score = 0.4*(Piotroski/9*100) + 0.3*(clip(AltmanZ,0,10)/10*100)
                          + 0.3*(clip(업사이드%,-20,50) 정규화)
  KR: fundamental_score = 0.5*(Piotroski/9*100) + 0.5*(clip(AltmanZ,0,10)/10*100)
                          (애널리스트 목표주가 DART 미제공으로 제외)
"""
import json
from pathlib import Path
import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def kr_fundamental_score(piotroski, altman_z):
    p_part = 0.5 * (piotroski / 9 * 100)
    z_clip = max(0, min(altman_z, 10))
    z_part = 0.5 * (z_clip / 10 * 100)
    return round(p_part + z_part, 1)


def main():
    us = json.loads((DATA_DIR / "fundamental_us.json").read_text(encoding="utf-8"))
    kr = json.loads((DATA_DIR / "fundamental_kr.json").read_text(encoding="utf-8"))
    sig = json.loads((DATA_DIR / "signals.json").read_text(encoding="utf-8"))

    us_by_ticker = {r["ticker"]: r for r in us["results"]}
    kr_by_ticker = {r["ticker"]: r for r in kr}

    rows = []
    for s in sig["signals"]:
        market = s.get("market", "US")
        ticker = s["symbol"].split(".")[0] if market == "KR" else s["symbol"]
        tech_score = s["score"]

        if market == "US" and ticker in us_by_ticker:
            f = us_by_ticker[ticker]
            fscore = f["fundamental_score"]
            piotroski = f["piotroski"]
            altman_z = f["altman_z"]
            upside = f["upside_pct"]
        elif market == "KR" and ticker in kr_by_ticker:
            f = kr_by_ticker[ticker]
            piotroski = f["piotroski"]
            altman_z = f["altman_z"]
            upside = None
            fscore = kr_fundamental_score(piotroski, altman_z)
        else:
            continue

        final_score = round(0.5 * fscore + 0.5 * tech_score, 1)
        rows.append({
            "market": market,
            "ticker": ticker,
            "name": s["name"],
            "piotroski": piotroski,
            "altman_z": altman_z,
            "upside_pct": upside,
            "fundamental_score": fscore,
            "tech_score": tech_score,
            "final_score": final_score,
        })

    rows.sort(key=lambda r: r["final_score"], reverse=True)

    out = {
        "generated_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + " (자동 생성)",
        "methodology": {
            "US": "fundamental_score = 0.4*(Piotroski/9*100) + 0.3*(clip(AltmanZ,0,10)/10*100) + 0.3*(clip(목표주가업사이드%,-20,50) 정규화); final_score = 0.5*fundamental + 0.5*기술점수(보정)",
            "KR": "fundamental_score = 0.5*(Piotroski/9*100) + 0.5*(clip(AltmanZ,0,10)/10*100) — 애널리스트 목표주가 불가능(DART 미제공)으로 제외; final_score = 0.5*fundamental + 0.5*기술점수(보정)",
            "tech_score_source": "signal_engine.py 매일 자동 실행 결과(보정 점수), data/signals.json",
            "limitation": "US/KR 펀더멘털 산식이 달라 fundamental_score 직접 비교는 참고용. Altman Z는 미국 제조업 기준 모델이라 한국 대기업 저평가 편향 있음.",
        },
        "rows": rows,
    }

    out_path = DATA_DIR / "combined_probability_table.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {out_path} ({len(rows)}행)")


if __name__ == "__main__":
    main()
