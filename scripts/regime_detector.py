#!/usr/bin/env python3
"""
Influence Radar — 시장 국면 감지 (Regime Detector)
════════════════════════════════════════════════════════════
AI 트레이딩 실패 원인 #1 극복: 국면 변화 맹목성 (Regime Blindness)
→ 해결책: 실시간 시장 국면 감지 → 불리한 환경에서 신호 임계값 자동 강화

국면 분류 (4가지):
  BULL     — 추세 상승 + 저변동성 → BUY 기준 정상 (65%)
  SIDEWAYS — 횡보 구간            → BUY 기준 강화 (70%)
  VOLATILE — 고변동성 공포 구간   → BUY 기준 대폭 강화 (75%)
  BEAR     — 추세 하락            → BUY 기준 최대 억제 (80%)

논리 근거:
  - 44%의 AI 트레이딩 전략이 국면 변화 미대응으로 실패 (2025 연구)
  - VIX 200MA 국면 필터: 드로다운 35% 감소, 샤프비율 향상
  - 국면별 전용 모델 적용 시 수익 일관성 유의미하게 향상

사용:
  python scripts/regime_detector.py
  → data/market_regime.json 저장
"""

import json, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

OUTPUT_PATH = "data/market_regime.json"

# 국면별 신호 임계값 조정
REGIME_THRESHOLDS = {
    "BULL":     {"buy": 0.65, "watch": 0.50},  # 정상 운영
    "SIDEWAYS": {"buy": 0.70, "watch": 0.55},  # 조건 강화
    "VOLATILE": {"buy": 0.75, "watch": 0.60},  # 대폭 강화
    "BEAR":     {"buy": 0.80, "watch": 0.65},  # 최대 억제
}

# 국면별 감점 계수 (BUY 신호 점수에 곱함)
REGIME_SCORE_MULTIPLIER = {
    "BULL":     1.00,
    "SIDEWAYS": 0.93,
    "VOLATILE": 0.85,
    "BEAR":     0.75,
}


def fetch_market_data(symbol, days=252):
    """시장 데이터 수집"""
    try:
        end   = datetime.today()
        start = (end - timedelta(days=days + 30)).strftime("%Y-%m-%d")
        df = yf.Ticker(symbol).history(start=start, auto_adjust=True)
        if df.empty or len(df) < 50:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception as e:
        print(f"  ⚠ {symbol} 수집 실패: {e}")
        return None


def calc_regime(df, label=""):
    """단일 시장 국면 감지 (MA + 변동성 + 모멘텀)"""
    close  = df['Close']
    high   = df['High']
    low    = df['Low']

    # ① 이동평균 관계
    ma50   = close.rolling(50).mean().iloc[-1]
    ma200  = close.rolling(200).mean().iloc[-1]
    price  = float(close.iloc[-1])
    above_ma200  = price > ma200
    golden_cross = ma50 > ma200

    # ② 변동성 (20일 실현 변동성 연율화)
    rets        = close.pct_change().dropna()
    vol_20      = float(rets.rolling(20).std().iloc[-1])  * np.sqrt(252) * 100
    vol_1y_avg  = float(rets.rolling(252).std().iloc[-1]) * np.sqrt(252) * 100
    vol_ratio   = vol_20 / (vol_1y_avg + 0.01)

    # ③ 30일 수익률
    ret_30d = float((close.iloc[-1] - close.iloc[-31]) / (close.iloc[-31] + 1e-9)) \
              if len(close) > 31 else 0

    # ④ ATR 기반 추세 강도 (ADX proxy)
    tr      = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr14   = float(tr.rolling(14).mean().iloc[-1])
    rng14   = float(high.rolling(14).max().iloc[-1] - low.rolling(14).min().iloc[-1])
    adx_proxy = min(rng14 / (atr14 * 14 + 1e-9), 3.0)

    # ⑤ 국면 점수 계산
    s_bull = 0.0
    s_bear = 0.0
    s_vol  = 0.0

    # 추세 신호 (40%)
    if above_ma200 and golden_cross:
        s_bull += 0.40
    elif not above_ma200:
        s_bear += 0.35
    else:
        s_bull += 0.15

    # 단기 모멘텀 (20%)
    if ret_30d > 0.03:
        s_bull += 0.20
    elif ret_30d < -0.05:
        s_bear += 0.20

    # 변동성 (30%)
    if vol_ratio > 1.5:       # 변동성 50%+ 초과 → VOLATILE
        s_vol  += 0.30
    elif vol_ratio < 0.8:     # 저변동성 → 안정 BULL 가산
        s_bull += 0.20

    # 추세 강도 (10%)
    if adx_proxy > 1.2:
        if ret_30d > 0:
            s_bull += 0.10
        else:
            s_bear += 0.10

    total = s_bull + s_bear + s_vol
    scores = {
        "BULL":     round(s_bull, 3),
        "BEAR":     round(s_bear, 3),
        "VOLATILE": round(s_vol,  3),
        "SIDEWAYS": round(max(0.0, 1.0 - total), 3),
    }

    regime     = max(scores, key=scores.get)
    confidence = scores[regime]

    return regime, confidence, scores, {
        "price":        round(price, 2),
        "ma50":         round(float(ma50), 2),
        "ma200":        round(float(ma200), 2),
        "vol_20d_ann":  round(vol_20, 1),
        "vol_1y_ann":   round(vol_1y_avg, 1),
        "vol_ratio":    round(vol_ratio, 2),
        "ret_30d_pct":  round(ret_30d * 100, 2),
        "above_ma200":  bool(above_ma200),
        "golden_cross": bool(golden_cross),
    }


def detect_regimes():
    """미국/한국 시장 국면 동시 감지 → data/market_regime.json 저장"""
    print("=" * 65)
    print("🌐 시장 국면 감지 — Regime Detector")
    print("=" * 65)

    result = {
        "detected_at": datetime.now().isoformat(),
        "us":          None,
        "kr":          None,
        "combined":    None,
    }

    # ── 미국 시장 (SPY)
    print("\n▸ 미국 시장 (SPY) ...")
    df_spy = fetch_market_data("SPY")
    if df_spy is not None:
        regime, conf, scores, metrics = calc_regime(df_spy, "US")
        result["us"] = {
            "regime":     regime,
            "confidence": round(conf, 3),
            "scores":     scores,
            "metrics":    metrics,
            "thresholds": REGIME_THRESHOLDS[regime],
        }
        print(f"  🇺🇸 미국 국면: {regime}  (신뢰도 {conf*100:.0f}%)")
        print(f"     30일수익 {metrics['ret_30d_pct']:+.1f}%  변동성비율 {metrics['vol_ratio']:.2f}")

    # ── 한국 시장 (KODEX 200)
    print("\n▸ 한국 시장 (KODEX200, 069500.KS) ...")
    df_kr = fetch_market_data("069500.KS")
    if df_kr is not None:
        regime, conf, scores, metrics = calc_regime(df_kr, "KR")
        result["kr"] = {
            "regime":     regime,
            "confidence": round(conf, 3),
            "scores":     scores,
            "metrics":    metrics,
            "thresholds": REGIME_THRESHOLDS[regime],
        }
        print(f"  🇰🇷 한국 국면: {regime}  (신뢰도 {conf*100:.0f}%)")
        print(f"     30일수익 {metrics['ret_30d_pct']:+.1f}%  변동성비율 {metrics['vol_ratio']:.2f}")

    # ── 통합 국면 (더 보수적인 쪽 선택)
    priority = {"BULL": 3, "SIDEWAYS": 2, "VOLATILE": 1, "BEAR": 0}
    all_reg  = []
    if result["us"]:
        all_reg.append((result["us"]["regime"], result["us"]["confidence"]))
    if result["kr"]:
        all_reg.append((result["kr"]["regime"], result["kr"]["confidence"]))

    if all_reg:
        combined_r, combined_c = min(all_reg, key=lambda x: priority.get(x[0], 2))
    else:
        combined_r, combined_c = "SIDEWAYS", 0.5

    combined_thresh = REGIME_THRESHOLDS[combined_r]
    multiplier      = REGIME_SCORE_MULTIPLIER[combined_r]

    result["combined"] = {
        "regime":           combined_r,
        "confidence":       round(combined_c, 3),
        "thresholds":       combined_thresh,
        "score_multiplier": multiplier,
        "note": (
            "🔴 비관적 국면 — BUY 기준 강화됨" if combined_r in ["BEAR", "VOLATILE"]
            else "🟡 횡보 — BUY 조건 약간 강화" if combined_r == "SIDEWAYS"
            else "🟢 강세 — 정상 운영"
        ),
    }

    print(f"\n{'='*65}")
    print(f"🔮 통합 국면: {combined_r}  (신뢰도 {combined_c*100:.0f}%)")
    print(f"   BUY 기준:   {combined_thresh['buy']*100:.0f}%")
    print(f"   WATCH 기준: {combined_thresh['watch']*100:.0f}%")
    print(f"   점수 보정:  {multiplier:.2f}x")
    print(f"   상태: {result['combined']['note']}")

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n💾 저장: {OUTPUT_PATH}")
    print("=" * 65)

    return result


if __name__ == "__main__":
    detect_regimes()
