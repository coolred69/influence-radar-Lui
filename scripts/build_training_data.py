#!/usr/bin/env python3
"""
Influence Radar — 실데이터 훈련셋 빌더
────────────────────────────────────────
알려진 인플루언서 이벤트 목록 + yfinance OHLCV
→ RSI / MACD / 볼린저밴드 / 거래량 / 모멘텀 자동 계산
→ 10일/20일 후 수익 결과 판정
→ data/training_data.json 저장

사용:
  pip install yfinance pandas numpy
  python scripts/build_training_data.py
"""

import json, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

OUTPUT_PATH  = "data/training_data.json"
HOLD_DAYS    = 10    # 신호 후 N일 결과로 outcome 판정
TARGET_RET   = 0.03  # 목표 수익률 3% (이상이면 outcome=1)

# ─────────────────────────────────────────────
# 알려진 인플루언서 이벤트 목록
# 형식: (날짜, 인물, 종목 Yahoo심볼, 신호유형, 감정, 섹터, 검증출처수)
# ─────────────────────────────────────────────

EVENTS = [
    # ── 🇰🇷 한국 ─────────────────────────────────────────────────
    # 이재용 (삼성전자)
    ("2024-01-15", "이재용",   "005930.KS", "실적발표예고", "positive", "KR_SEMICON", 4),
    ("2024-03-20", "이재용",   "005930.KS", "AI칩 투자발표", "positive", "KR_SEMICON", 5),
    ("2024-05-10", "이재용",   "005930.KS", "글로벌파트너십", "positive", "KR_SEMICON", 3),
    ("2024-07-08", "이재용",   "000660.KS", "HBM 공급확대", "positive", "KR_SEMICON", 4),
    ("2024-09-12", "이재용",   "005930.KS", "실적부진 우려", "negative", "KR_SEMICON", 5),
    ("2024-11-05", "이재용",   "005930.KS", "파운드리 전략",  "positive", "KR_SEMICON", 3),
    ("2025-01-20", "이재용",   "005930.KS", "AI메모리 수요증가", "positive", "KR_SEMICON", 5),
    ("2025-03-15", "이재용",   "000660.KS", "HBM4 개발완료", "positive", "KR_SEMICON", 4),

    # 정의선 (현대차/기아)
    ("2024-02-14", "정의선",   "005380.KS", "전기차 판매목표", "positive", "KR_AUTO", 4),
    ("2024-04-22", "정의선",   "000270.KS", "북미시장 확대",   "positive", "KR_AUTO", 3),
    ("2024-06-18", "정의선",   "005380.KS", "배터리내재화",    "positive", "KR_BATTERY", 4),
    ("2024-08-27", "정의선",   "000270.KS", "전기차 수요둔화", "negative", "KR_AUTO", 5),
    ("2024-10-14", "정의선",   "005380.KS", "로보틱스투자",    "positive", "KR_AUTO", 3),
    ("2025-02-10", "정의선",   "000270.KS", "하이브리드전략",  "positive", "KR_AUTO", 4),

    # 최태원 (SK하이닉스/SK이노베이션)
    ("2024-03-07", "최태원",   "000660.KS", "AI반도체 수혜",   "positive", "KR_SEMICON", 5),
    ("2024-06-03", "최태원",   "096770.KS", "배터리사업재편",  "positive", "KR_BATTERY", 3),
    ("2024-09-23", "최태원",   "000660.KS", "HBM 점유율확대",  "positive", "KR_SEMICON", 5),
    ("2025-01-08", "최태원",   "000660.KS", "엔비디아 공급망", "positive", "KR_SEMICON", 5),

    # 이재명 (정책 수혜주)
    ("2024-04-11", "이재명",   "373220.KS", "배터리산업육성",  "positive", "KR_BATTERY", 4),
    ("2024-07-15", "이재명",   "005380.KS", "전기차 보조금확대","positive","KR_AUTO", 3),
    ("2024-10-28", "이재명",   "000660.KS", "반도체 국가지원", "positive", "KR_SEMICON", 4),
    ("2025-03-05", "이재명",   "373220.KS", "K배터리 정책",    "positive", "KR_BATTERY", 5),
    ("2025-05-12", "이재명",   "005930.KS", "반도체 세제지원", "positive", "KR_SEMICON", 4),

    # ── 🇺🇸 미국 ─────────────────────────────────────────────────
    # Jensen Huang (NVIDIA)
    ("2024-01-08", "Jensen Huang", "NVDA", "CES기조연설 AI칩",    "positive", "AI/GPU", 6),
    ("2024-03-18", "Jensen Huang", "NVDA", "GTC H200 발표",       "positive", "AI/GPU", 6),
    ("2024-05-22", "Jensen Huang", "NVDA", "실적서프라이즈",       "positive", "AI/GPU", 6),
    ("2024-08-28", "Jensen Huang", "NVDA", "Blackwell 출하지연",   "negative", "AI/GPU", 5),
    ("2024-11-20", "Jensen Huang", "NVDA", "FQ3 실적발표",        "positive", "AI/GPU", 6),
    ("2025-01-06", "Jensen Huang", "NVDA", "CES2025 GB200",       "positive", "AI/GPU", 6),
    ("2025-03-17", "Jensen Huang", "NVDA", "GTC2025 Blackwell",   "positive", "AI/GPU", 6),

    # Elon Musk (Tesla)
    ("2024-01-24", "Elon Musk", "TSLA", "실적실망 마진압박",  "negative", "EV/Auto", 5),
    ("2024-04-23", "Elon Musk", "TSLA", "저가모델 개발계획", "positive", "EV/Auto", 5),
    ("2024-07-23", "Elon Musk", "TSLA", "로보택시 발표",     "positive", "EV/Auto", 5),
    ("2024-10-10", "Elon Musk", "TSLA", "로보택시 데이",     "positive", "EV/Auto", 6),
    ("2025-01-29", "Elon Musk", "TSLA", "Q4 실적발표",       "negative", "EV/Auto", 5),

    # Jerome Powell (Fed)
    ("2024-01-31", "Jerome Powell", "SPY", "금리동결 매파적",  "negative", "Macro/Rates", 6),
    ("2024-03-20", "Jerome Powell", "QQQ", "금리인하 시사",    "positive", "Macro/Rates", 6),
    ("2024-09-18", "Jerome Powell", "SPY", "빅컷 0.5%인하",   "positive", "Macro/Rates", 6),
    ("2024-12-18", "Jerome Powell", "SPY", "인하속도 조절",   "negative", "Macro/Rates", 6),
    ("2025-01-29", "Jerome Powell", "QQQ", "금리동결 유지",   "neutral",  "Macro/Rates", 5),

    # Sam Altman (OpenAI 관련주)
    ("2024-02-15", "Sam Altman", "MSFT", "Azure AI수요급증", "positive", "Cloud/AI", 5),
    ("2024-05-13", "Sam Altman", "MSFT", "GPT-4o 발표",     "positive", "Cloud/AI", 5),
    ("2024-09-12", "Sam Altman", "NVDA", "칩수요 발언",      "positive", "AI/GPU", 4),
    ("2025-01-21", "Sam Altman", "MSFT", "Stargate 500B",  "positive", "Cloud/AI", 6),
    ("2025-02-10", "Sam Altman", "NVDA", "o3 모델 발표",    "positive", "AI/GPU", 5),

    # Warren Buffett
    ("2024-02-24", "Warren Buffett", "BRK-B", "연례서한 발표",  "positive", "Finance", 5),
    ("2024-05-04", "Warren Buffett", "AAPL",  "애플매도 발표",  "negative", "Tech/Finance", 6),
    ("2024-08-14", "Warren Buffett", "AAPL",  "애플지분 추가매도","negative","Tech/Finance",6),
    ("2025-02-22", "Warren Buffett", "BRK-B", "현금비축 발표",   "neutral", "Finance", 5),
]

# ─────────────────────────────────────────────
# 기술적 지표 계산
# ─────────────────────────────────────────────

def calc_rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def calc_macd_signal(close: pd.Series) -> int:
    """MACD 방향 일치 여부: 1=골든크로스/MACD양수, 0=데드크로스/MACD음수"""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    if len(macd) < 2: return 0
    # MACD가 시그널선 위로 올라오면 1
    return 1 if (macd.iloc[-1] > signal_line.iloc[-1] and macd.iloc[-2] <= signal_line.iloc[-2]) \
             or macd.iloc[-1] > 0 else 0

def calc_volume_surge(volume: pd.Series, window=20) -> float:
    """거래량 / 20일 평균거래량 (배율)"""
    avg = volume.rolling(window).mean().iloc[-1]
    return float(volume.iloc[-1] / (avg + 1)) if avg > 0 else 1.0

def calc_bollinger_pos(close: pd.Series, window=20) -> float:
    """볼린저밴드 내 위치 0~1 (0=하단, 0.5=중앙, 1=상단 이상)"""
    ma   = close.rolling(window).mean()
    std  = close.rolling(window).std()
    upper = ma + 2*std
    lower = ma - 2*std
    pos  = (close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-9)
    return float(np.clip(pos, 0, 1))

def calc_momentum(close: pd.Series, days=5) -> float:
    """N일 가격 모멘텀 (등락률 0~1 정규화)"""
    if len(close) < days+1: return 0.5
    ret = (close.iloc[-1] - close.iloc[-(days+1)]) / (close.iloc[-(days+1)] + 1e-9)
    return float(np.clip(0.5 + ret * 5, 0, 1))  # ±10% → 0~1

# ─────────────────────────────────────────────
# 이벤트 → 훈련 데이터 변환
# ─────────────────────────────────────────────

def fetch_event_data(date_str, symbol, hold_days=HOLD_DAYS):
    """
    이벤트 날짜 기준 과거 60일 OHLCV 로드 → 지표 계산 + 결과 판정
    """
    try:
        signal_date = datetime.strptime(date_str, "%Y-%m-%d")
        start = (signal_date - timedelta(days=90)).strftime("%Y-%m-%d")
        end   = (signal_date + timedelta(days=hold_days + 5)).strftime("%Y-%m-%d")

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, auto_adjust=True)

        if df.empty or len(df) < 20:
            print(f"  ⚠ {symbol} {date_str}: 데이터 없음")
            return None

        # 신호일과 가장 가까운 거래일 찾기
        df.index = pd.to_datetime(df.index).tz_localize(None)
        signal_dt = pd.Timestamp(signal_date)

        # 신호일 이후 첫 거래일
        after = df[df.index >= signal_dt]
        if after.empty:
            print(f"  ⚠ {symbol} {date_str}: 신호일 이후 데이터 없음")
            return None

        signal_idx  = after.index[0]
        signal_pos  = df.index.get_loc(signal_idx)
        signal_price = float(df['Close'].iloc[signal_pos])

        # 신호일까지의 데이터 (지표 계산용)
        pre = df.iloc[:signal_pos+1]
        if len(pre) < 20:
            print(f"  ⚠ {symbol} {date_str}: 사전 데이터 부족")
            return None

        # 결과일 (N 거래일 후)
        result_pos = min(signal_pos + hold_days, len(df) - 1)
        result_price = float(df['Close'].iloc[result_pos])
        actual_return = (result_price - signal_price) / (signal_price + 1e-9)

        # 기술적 지표
        close  = pre['Close']
        volume = pre['Volume']

        rsi     = calc_rsi(close)
        macd    = calc_macd_signal(close)
        vol_surge = calc_volume_surge(volume)
        boll    = calc_bollinger_pos(close)
        mom5    = calc_momentum(close, 5)

        # RSI 매수구간 (30~60이면 진입 적정)
        rsi_filter = 1 if 25 <= rsi <= 65 else 0
        vol_flag   = 1 if vol_surge >= 1.5 else 0

        return {
            "signal_price":  round(signal_price, 4),
            "result_price":  round(result_price, 4),
            "actual_return": round(actual_return * 100, 2),
            "outcome":       1 if actual_return >= TARGET_RET else 0,
            "indicators": {
                "rsi_raw":      round(rsi, 1),
                "rsi_filter":   float(rsi_filter),
                "macd_align":   float(macd),
                "volume_surge": round(min(vol_flag, 1.0), 3),
                "volume_ratio": round(min(vol_surge / 3.0, 1.0), 3),  # 3배 상한 정규화
                "bollinger_pos": round(boll, 3),
                "momentum_5d":  round(mom5, 3),
            }
        }

    except Exception as e:
        print(f"  ❌ {symbol} {date_str}: {e}")
        return None


# ─────────────────────────────────────────────
# 인플루언서별 hit_rate 계산
# ─────────────────────────────────────────────

def compute_person_hit_rates(results):
    """처리된 이벤트로부터 인물별 과거 적중률 계산"""
    from collections import defaultdict
    stats = defaultdict(lambda: {"total":0, "hit":0})
    for r in results:
        p = r["person"]
        stats[p]["total"] += 1
        if r["outcome"] == 1:
            stats[p]["hit"] += 1
    return {p: s["hit"]/s["total"] if s["total"] else 0.5 for p, s in stats.items()}


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("📊 훈련 데이터 빌더 — 실이벤트 + 실가격")
    print("=" * 60)
    print(f"총 이벤트: {len(EVENTS)}건  |  보유기간: {HOLD_DAYS}일  |  목표수익: {TARGET_RET*100}%\n")

    raw_results = []

    for i, (date_str, person, symbol, statement, sentiment, sector, cross_val) in enumerate(EVENTS):
        print(f"[{i+1:02d}/{len(EVENTS)}] {person:15s} {symbol:12s} {date_str} — {statement}")
        data = fetch_event_data(date_str, symbol)
        if data is None:
            continue

        # 감정 → 숫자
        sent_map = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
        sent_val = sent_map.get(sentiment, 0.5)

        raw_results.append({
            "date":      date_str,
            "person":    person,
            "symbol":    symbol,
            "statement": statement,
            "sector":    sector,
            "sentiment": sentiment,
            "cross_val_raw": cross_val,
            "outcome":   data["outcome"],
            "signal_price":  data["signal_price"],
            "result_price":  data["result_price"],
            "actual_return": data["actual_return"],
            "indicators_raw": data["indicators"],  # 기술지표 원본
            "_sent_val":  sent_val,
            "_cross_norm": min(cross_val / 6.0, 1.0),
        })

        ret_str = f"+{data['actual_return']}%" if data['actual_return'] >= 0 else f"{data['actual_return']}%"
        out_str = "✅" if data["outcome"] == 1 else "❌"
        print(f"       → {out_str} {ret_str}  RSI:{data['indicators']['rsi_raw']}  MACD:{data['indicators']['macd_align']}  Vol:{data['indicators']['volume_ratio']:.2f}x")

    if not raw_results:
        print("\n❌ 처리된 이벤트 없음. yfinance 설치 확인: pip install yfinance")
        return

    # hit_rate 계산 후 전체 indicators 완성
    hit_rates = compute_person_hit_rates(raw_results)

    final_signals = []
    for r in raw_results:
        hr = hit_rates.get(r["person"], 0.5)
        ind = r["indicators_raw"].copy()
        ind["hit_rate"]        = round(hr, 3)
        ind["sentiment"]       = r["_sent_val"]
        ind["cross_val"]       = r["_cross_norm"]
        ind["news_freq"]       = round(min(r["cross_val_raw"] / 6.0, 1.0), 3)
        ind["influence_score"] = 0.80  # 추후 data.js 인물 데이터와 연동
        ind["signal_strength"] = round((r["_sent_val"] + ind["macd_align"] + ind["rsi_filter"]) / 3.0, 3)
        ind["market_regime"]   = 1     # 추후 KOSPI/S&P 트렌드로 교체

        final_signals.append({
            "id":           len(final_signals),
            "date":         r["date"],
            "person":       r["person"],
            "symbol":       r["symbol"],
            "sector":       r["sector"],
            "sentiment":    r["sentiment"],
            "statement":    r["statement"],
            "outcome":      r["outcome"],
            "signal_price": r["signal_price"],
            "result_price": r["result_price"],
            "actual_return": r["actual_return"],
            "indicators":   ind,
        })

    # 통계 요약
    total = len(final_signals)
    wins  = sum(s["outcome"] for s in final_signals)
    print(f"\n{'='*60}")
    print(f"✅ 처리 완료: {total}건  |  수익달성: {wins}건 ({wins/total*100:.1f}%)")

    # 인물별 적중률
    print(f"\n  {'인물':<20} {'신호':>5} {'적중':>5} {'적중률':>8}")
    print(f"  {'─'*42}")
    for person, hr in sorted(hit_rates.items(), key=lambda x:-x[1]):
        sigs = [s for s in final_signals if s["person"] == person]
        hits = sum(s["outcome"] for s in sigs)
        print(f"  {person:<20} {len(sigs):>5} {hits:>5} {hr*100:>7.1f}%")

    # 저장
    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at":  datetime.now().isoformat(),
        "total_signals": total,
        "positive_rate": round(wins/total, 3),
        "hold_days":     HOLD_DAYS,
        "target_return": TARGET_RET,
        "hit_rates_by_person": {k: round(v,3) for k,v in hit_rates.items()},
        "signals": final_signals,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n💾 저장 완료: {OUTPUT_PATH} ({total}건)")
    print("다음 단계: python scripts/indicator_lab.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
