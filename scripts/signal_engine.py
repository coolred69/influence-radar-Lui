#!/usr/bin/env python3
"""
Influence Radar — Signal Engine
════════════════════════════════════════════════════════════
IR-COORD 가중치 + 실시간 OHLCV → 매수 신호 자동 생성

파이프라인:
  1. data/indicator_results.json → 최적 가중치(IR-COORD) 로드
  2. WATCHLIST 각 종목 → yfinance 현재 OHLCV 수집
  3. 12개 지표 계산
  4. 복합 점수 산출 (0~100%)
  5. BUY(≥65%) / WATCH(50~65%) / WAIT(<50%) 신호 발생
  6. data/signals.json 저장

사용:
  python scripts/signal_engine.py
"""

import json, os, math
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

RESULTS_PATH  = "data/indicator_results.json"
TRAINING_PATH = "data/training_data.json"
OUTPUT_PATH   = "data/signals.json"
HISTORY_PATH  = "data/signal_history.json"
PARAMS_PATH   = "data/optimal_params.json"
REGIME_PATH   = "data/market_regime.json"

BUY_THRESHOLD   = 0.65
WATCH_THRESHOLD = 0.50

# ──────────────────────────────────────────────────────────────
# 감시 종목 목록
# ──────────────────────────────────────────────────────────────
WATCHLIST = [
    # ── 🇰🇷 한국 ──
    {"symbol": "005930.KS", "name": "삼성전자",       "influencer": "이재용",  "sector": "KR_SEMICON", "market": "KR"},
    {"symbol": "000660.KS", "name": "SK하이닉스",     "influencer": "최태원",  "sector": "KR_SEMICON", "market": "KR"},
    {"symbol": "005380.KS", "name": "현대차",          "influencer": "정의선",  "sector": "KR_AUTO",    "market": "KR"},
    {"symbol": "000270.KS", "name": "기아",             "influencer": "정의선",  "sector": "KR_AUTO",    "market": "KR"},
    {"symbol": "373220.KS", "name": "LG에너지솔루션", "influencer": "구광모",  "sector": "KR_BATTERY", "market": "KR"},
    {"symbol": "035720.KS", "name": "카카오",          "influencer": "김범수",  "sector": "KR_TECH",    "market": "KR"},
    {"symbol": "035420.KS", "name": "네이버",          "influencer": "최수연",  "sector": "KR_TECH",    "market": "KR"},
    {"symbol": "096770.KS", "name": "SK이노베이션",    "influencer": "최태원",  "sector": "KR_BATTERY", "market": "KR"},
    {"symbol": "207940.KS", "name": "삼성바이오로직스","influencer": "이재용",  "sector": "KR_BIO",     "market": "KR"},
    {"symbol": "051910.KS", "name": "LG화학",         "influencer": "구광모",  "sector": "KR_BATTERY", "market": "KR"},
    # ── 🇺🇸 미국 ──
    {"symbol": "NVDA",  "name": "NVIDIA",      "influencer": "Jensen Huang",    "sector": "AI/GPU",     "market": "US"},
    {"symbol": "TSLA",  "name": "Tesla",        "influencer": "Elon Musk",       "sector": "EV/Auto",    "market": "US"},
    {"symbol": "AAPL",  "name": "Apple",        "influencer": "Tim Cook",        "sector": "Tech",       "market": "US"},
    {"symbol": "MSFT",  "name": "Microsoft",    "influencer": "Satya Nadella",   "sector": "Cloud/AI",   "market": "US"},
    {"symbol": "META",  "name": "Meta",         "influencer": "Mark Zuckerberg", "sector": "Social/AI",  "market": "US"},
    {"symbol": "AMD",   "name": "AMD",          "influencer": "Jensen Huang",    "sector": "AI/GPU",     "market": "US"},
    {"symbol": "AMZN",  "name": "Amazon",       "influencer": "Andy Jassy",      "sector": "Cloud/AI",   "market": "US"},
    {"symbol": "GOOGL", "name": "Alphabet",     "influencer": "Sundar Pichai",   "sector": "Cloud/AI",   "market": "US"},
    {"symbol": "SPY",   "name": "S&P500 ETF",   "influencer": "Jerome Powell",   "sector": "Macro",      "market": "US"},
    {"symbol": "QQQ",   "name": "Nasdaq ETF",   "influencer": "Jerome Powell",   "sector": "Macro",      "market": "US"},
]

# 인물별 기본 적중률 (training_data.json 없을 때 사용)
DEFAULT_HIT_RATES = {
    "Jensen Huang":    0.82,
    "이재용":           0.65,
    "최태원":           0.72,
    "정의선":           0.58,
    "Tim Cook":        0.67,
    "Satya Nadella":   0.73,
    "Sam Altman":      0.70,
    "Jerome Powell":   0.60,
    "Elon Musk":       0.54,
    "Mark Zuckerberg": 0.68,
    "Warren Buffett":  0.62,
    "구광모":           0.60,
    "김범수":           0.44,
    "최수연":           0.50,
    "이재명":           0.55,
    "Donald Trump":    0.52,
    "Andy Jassy":      0.65,
    "Sundar Pichai":   0.64,
}

# ──────────────────────────────────────────────────────────────
# 가중치 로드
# ──────────────────────────────────────────────────────────────

def load_weights():
    """IR-COORD 가중치 로드 — 역대 최고 AUC Gen 우선 사용."""
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            data = json.load(f)

        best = data.get("best_ever", {})
        current_auc = data.get("optimal_metrics", {}).get("auc", 0)
        best_auc    = best.get("metrics", {}).get("auc", 0)

        # 역대 최고가 현재보다 나으면 best 사용
        if best and best_auc >= current_auc:
            weights   = best.get("weights", {})
            coord_sig = best.get("coordinate_sig", "IR-COORD-DEFAULT")
            gen       = best.get("generation", 0)
            print(f"🏆 역대 최고 좌표 사용: {coord_sig}  (Gen {gen}, AUC {best_auc:.4f})")
        else:
            weights   = data.get("optimal_weights", {})
            coord_sig = data.get("coordinate_sig", "IR-COORD-DEFAULT")
            gen       = data.get("generation", 0)
            print(f"✅ 현재 좌표 사용: {coord_sig}  (Gen {gen}, AUC {current_auc:.4f})")

        if weights:
            return weights, coord_sig, gen

    # 기본 균등 가중치
    default_keys = ["rsi_filter","macd_align","volume_surge","volume_ratio",
                    "bollinger_pos","momentum_5d","sentiment","hit_rate","signal_strength"]
    w = {k: round(1/len(default_keys), 4) for k in default_keys}
    print("⚠ indicator_results.json 없음. 균등 가중치 사용.")
    return w, "IR-COORD-DEFAULT", 0

def load_regime():
    """시장 국면 로드 → BUY/WATCH 임계값 동적 조정"""
    default = {
        "regime":           "SIDEWAYS",
        "thresholds":       {"buy": 0.65, "watch": 0.50},
        "score_multiplier": 1.0,
        "note":             "국면 데이터 없음 — 기본값 사용",
    }
    if not os.path.exists(REGIME_PATH):
        return default
    try:
        with open(REGIME_PATH) as f:
            data = json.load(f)
        combined = data.get("combined", {})
        if combined:
            return {
                "regime":           combined.get("regime", "SIDEWAYS"),
                "thresholds":       combined.get("thresholds", default["thresholds"]),
                "score_multiplier": combined.get("score_multiplier", 1.0),
                "note":             combined.get("note", ""),
            }
    except Exception:
        pass
    return default


def load_hit_rates():
    """training_data.json에서 인물별 적중률 로드."""
    if os.path.exists(TRAINING_PATH):
        with open(TRAINING_PATH) as f:
            data = json.load(f)
        hr = data.get("hit_rates_by_person", {})
        if hr:
            return hr
    return DEFAULT_HIT_RATES

# ──────────────────────────────────────────────────────────────
# 지표 계산 (build_training_data.py와 동일)
# ──────────────────────────────────────────────────────────────

def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

def calc_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / (loss + 1e-9)
    rsi   = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def calc_macd_signal(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    if len(macd) < 2: return 0
    return 1 if (macd.iloc[-1] > sig.iloc[-1] and macd.iloc[-2] <= sig.iloc[-2]) \
             or macd.iloc[-1] > 0 else 0

def calc_volume_ratio(volume, window=20):
    avg = volume.rolling(window).mean().iloc[-1]
    return float(min(volume.iloc[-1] / (avg + 1), 5.0) / 5.0) if avg > 0 else 0.5

def calc_volume_surge(volume, window=20):
    avg = volume.rolling(window).mean().iloc[-1]
    return 1.0 if volume.iloc[-1] / (avg + 1) >= 1.5 else 0.0

def calc_bollinger_pos(close, window=20):
    ma  = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = ma + 2*std; lower = ma - 2*std
    pos = (close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-9)
    return float(np.clip(pos, 0, 1))

def calc_momentum(close, days=5):
    if len(close) < days+1: return 0.5
    ret = (close.iloc[-1] - close.iloc[-(days+1)]) / (close.iloc[-(days+1)] + 1e-9)
    return float(np.clip(0.5 + ret * 5, 0, 1))

def calc_gap_up(df):
    if len(df) < 2: return 0.5
    prev_close = float(df['Close'].iloc[-2])
    today_open = float(df['Open'].iloc[-1])
    gap = (today_open - prev_close) / (prev_close + 1e-9)
    return float(np.clip(0.5 + gap * 10, 0, 1))

def calc_price_vs_52w(close):
    if len(close) < 10: return 0.5
    high_52w = close.rolling(min(len(close), 252)).max().iloc[-1]
    return float(np.clip(close.iloc[-1] / (high_52w + 1e-9), 0, 1))

def calc_atr_stability(df, window=14):
    high = df['High']; low = df['Low']; close = df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    ratio = atr / (close.iloc[-1] + 1e-9)
    return float(np.clip(1 - ratio * 10, 0, 1))

def calc_atr_raw(df, window=14):
    """실제 ATR 값 반환 (정규화 없이)"""
    high = df['High']; low = df['Low']; close = df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1])

def calc_support_level(close, window=20):
    """최근 N일 저점 (지지선)"""
    return float(close.rolling(window).min().iloc[-1])

def price_round(price, market):
    """시장별 가격 반올림"""
    if market == "KR":
        if price >= 100000: return round(price / 500) * 500
        if price >= 10000:  return round(price / 100) * 100
        return round(price / 50) * 50
    return round(price, 2)

def calc_trend_dir(close, window=20):
    if len(close) < window: return 0.5
    y = close.values[-window:]
    x = np.arange(window)
    slope = np.polyfit(x, y, 1)[0]
    return 1.0 if slope > 0 else 0.0

def calc_pre_run_inv(close, days=5):
    if len(close) < days+2: return 0.5
    ret = (close.iloc[-1] - close.iloc[-(days+1)]) / (close.iloc[-(days+1)] + 1e-9)
    return float(np.clip(0.5 - ret * 3, 0, 1))

# ──────────────────────────────────────────────────────────────
# 종목 스코어링
# ──────────────────────────────────────────────────────────────

def score_stock(item, weights, hit_rates):
    symbol     = item["symbol"]
    influencer = item["influencer"]

    try:
        end   = datetime.today()
        start = (end - timedelta(days=120)).strftime("%Y-%m-%d")
        df    = yf.Ticker(symbol).history(start=start, auto_adjust=True)
        if df.empty or len(df) < 25:
            return None

        df.index = pd.to_datetime(df.index).tz_localize(None)
        close  = df['Close']
        volume = df['Volume']

        # ── 현재가 & 등락
        price_now  = float(close.iloc[-1])
        price_prev = float(close.iloc[-2]) if len(close) > 1 else price_now
        change_pct = round((price_now - price_prev) / (price_prev + 1e-9) * 100, 2)

        # ── 12개 지표 계산
        rsi_val    = calc_rsi(close)
        rsi_filter = 1.0 if 28 <= rsi_val <= 65 else 0.0
        macd       = float(calc_macd_signal(close))
        vol_ratio  = round(calc_volume_ratio(volume), 3)
        vol_surge  = calc_volume_surge(volume)
        boll       = round(calc_bollinger_pos(close), 3)
        mom5       = round(calc_momentum(close, 5), 3)
        gap        = round(calc_gap_up(df), 3)
        vs_52w     = round(calc_price_vs_52w(close), 3)
        atr_stab   = round(calc_atr_stability(df), 3)
        trend      = calc_trend_dir(close, 20)
        pre_run    = round(calc_pre_run_inv(close, 5), 3)

        # ── 매매 레벨 계산 (ATR 기반)
        atr_raw      = calc_atr_raw(df)
        support      = calc_support_level(close, 20)
        market_code  = item.get("market", "US")
        entry_price  = price_round(max(price_now - 0.3 * atr_raw, support), market_code)
        target_price = price_round(price_now + 2.0 * atr_raw, market_code)
        stop_loss    = price_round(max(price_now - 1.0 * atr_raw, support * 0.98), market_code)
        rr_denom     = max(entry_price - stop_loss, price_now * 0.001)
        risk_reward  = round((target_price - entry_price) / rr_denom, 1)

        hr          = hit_rates.get(influencer, DEFAULT_HIT_RATES.get(influencer, 0.55))
        sig_str     = round((macd + rsi_filter + trend) / 3.0, 3)

        all_indicators = {
            "rsi_filter":    rsi_filter,
            "rsi_raw":       round(rsi_val, 1),
            "macd_align":    macd,
            "volume_surge":  vol_surge,
            "volume_ratio":  vol_ratio,
            "bollinger_pos": boll,
            "momentum_5d":   mom5,
            "gap_up":        gap,
            "price_vs_52w":  vs_52w,
            "atr_stability": atr_stab,
            "trend_dir_20":  trend,
            "pre_run_inv":   pre_run,
            "hit_rate":      round(hr, 3),
            "sentiment":     0.5,   # 현재 이벤트 없을 때 중립
            "signal_strength": sig_str,
            "news_freq":     0.5,
            "cross_val":     0.5,
        }

        # ── IR-COORD 적용
        score_raw = sum(weights[k] * all_indicators.get(k, 0.5)
                        for k in weights if k in all_indicators)
        # 가중치에 없는 키는 0.5로 폴백
        missing = [k for k in weights if k not in all_indicators]
        if missing:
            score_raw += sum(weights[k] * 0.5 for k in missing)

        prob = sigmoid((score_raw - 0.5) * 8)

        signal = "BUY"   if prob >= BUY_THRESHOLD   else \
                 "WATCH" if prob >= WATCH_THRESHOLD  else "WAIT"

        # ── 활성 지표 (점수에 가장 기여한 3개)
        contrib = {k: weights.get(k, 0) * all_indicators.get(k, 0.5) for k in weights}
        top3 = sorted(contrib, key=lambda x: -contrib[x])[:3]

        return {
            "symbol":     symbol,
            "name":       item["name"],
            "market":     item["market"],
            "influencer": influencer,
            "sector":     item["sector"],
            "price":      round(price_now, 2),
            "change_pct": change_pct,
            "score":      round(prob * 100, 1),
            "signal":     signal,
            "top_indicators": top3,
            "indicators": all_indicators,
            "entry_price":  entry_price,
            "target_price": target_price,
            "stop_loss":    stop_loss,
            "risk_reward":  risk_reward,
            "atr":          round(atr_raw, 2),
        }

    except Exception as e:
        print(f"  ❌ {symbol}: {e}")
        return None

# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("📡 Signal Engine — IR-COORD 기반 매수 신호 생성")
    print("=" * 65)

    weights, coord_sig, generation = load_weights()
    hit_rates = load_hit_rates()
    regime_info = load_regime()

    # 국면 기반 임계값 동적 조정
    regime_name   = regime_info["regime"]
    regime_buy    = regime_info["thresholds"]["buy"]
    regime_watch  = regime_info["thresholds"]["watch"]
    regime_mult   = regime_info["score_multiplier"]

    print(f"\n🌐 시장 국면: {regime_name}  "
          f"BUY기준 {regime_buy*100:.0f}%  WATCH기준 {regime_watch*100:.0f}%  "
          f"점수보정 {regime_mult:.2f}x")
    print(f"   {regime_info['note']}")

    # weight_info: 현재 vs 역대최고 정보 수집
    weight_info = {"current_sig": coord_sig, "current_gen": generation,
                   "current_weights": weights, "current_auc": 0}
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            _rd = json.load(f)
        weight_info["current_auc"] = _rd.get("optimal_metrics", {}).get("auc", 0)
        best = _rd.get("best_ever", {})
        if best:
            weight_info["best_sig"]     = best.get("coordinate_sig", coord_sig)
            weight_info["best_gen"]     = best.get("generation", generation)
            weight_info["best_weights"] = best.get("weights", weights)
            weight_info["best_auc"]     = best.get("metrics", {}).get("auc", 0)

    print(f"\n감시 종목: {len(WATCHLIST)}개\n")
    results = []
    for item in WATCHLIST:
        print(f"  {item['symbol']:12s} {item['name']:<18s} 분석 중...")
        r = score_stock(item, weights, hit_rates)
        if r:
            # 국면 보정 적용
            raw_score = r["score"]
            adj_score = round(raw_score * regime_mult, 1)
            r["score"] = adj_score
            r["score_raw"] = raw_score
            r["regime"] = regime_name

            # 국면 기반 신호 재판정
            prob_adj = adj_score / 100.0
            r["signal"] = ("BUY"   if prob_adj >= regime_buy   else
                           "WATCH" if prob_adj >= regime_watch else "WAIT")

            results.append(r)
            bar = "█" * int(adj_score / 5)
            adj_tag = f"(보정 {raw_score:.1f}→{adj_score:.1f})" if regime_mult != 1.0 else ""
            print(f"    → {r['signal']:5s}  {adj_score:5.1f}%  {bar}  "
                  f"{r['price']:>10.2f} ({r['change_pct']:+.2f}%) {adj_tag}")

    if not results:
        print("❌ 스코어링된 종목 없음")
        return

    # 점수 내림차순 정렬
    results.sort(key=lambda x: -x["score"])

    buy_list   = [r for r in results if r["signal"] == "BUY"]
    watch_list = [r for r in results if r["signal"] == "WATCH"]

    print(f"\n{'='*65}")
    print(f"🟢 BUY   {len(buy_list)}개: {', '.join(r['symbol'] for r in buy_list)}")
    print(f"🟡 WATCH {len(watch_list)}개: {', '.join(r['symbol'] for r in watch_list)}")

    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at": datetime.now().isoformat(),
        "coordinate_sig": coord_sig,
        "generation": generation,
        "buy_threshold":   regime_buy,
        "watch_threshold": regime_watch,
        "regime":          regime_name,
        "regime_note":     regime_info["note"],
        "score_multiplier": regime_mult,
        "total_scored": len(results),
        "buy_count":   len(buy_list),
        "watch_count": len(watch_list),
        "weight_info": weight_info,
        "signals": results,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── BUY 신호 히스토리 저장 (Phase 3 피드백 루프용)
    _save_signal_history(buy_list)

    print(f"\n💾 저장: {OUTPUT_PATH} ({len(results)}건)")
    print("=" * 65)


def _save_signal_history(buy_signals):
    """BUY 신호를 signal_history.json에 누적 저장"""
    existing = []
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH) as f:
                existing = json.load(f).get("signals", [])
        except Exception:
            existing = []

    existing_keys = {(s["date"], s["symbol"]) for s in existing}
    today = datetime.now().strftime("%Y-%m-%d")
    added = 0

    for s in buy_signals:
        key = (today, s["symbol"])
        if key in existing_keys:
            continue
        existing.append({
            "date":         today,
            "symbol":       s["symbol"],
            "name":         s.get("name", ""),
            "market":       s.get("market", ""),
            "sector":       s.get("sector", ""),
            "influencer":   s.get("influencer", ""),
            "signal":       "BUY",
            "score":        s.get("score", 0),
            "price":        s.get("price", 0),
            "entry_price":  s.get("entry_price", 0),
            "target_price": s.get("target_price", 0),
            "stop_loss":    s.get("stop_loss", 0),
            "risk_reward":  s.get("risk_reward", 0),
            "indicators":   s.get("indicators", {}),
            "coordinate_sig": s.get("coordinate_sig", ""),
            "evaluated":    False,
            "outcome":      None,
            "return_pct":   None,
        })
        existing_keys.add(key)
        added += 1

    if added > 0:
        os.makedirs("data", exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": datetime.now().isoformat(),
                "total": len(existing),
                "signals": existing
            }, f, indent=2, ensure_ascii=False)
        print(f"📝 BUY 히스토리 +{added}건 추가 (누계 {len(existing)}건)")

if __name__ == "__main__":
    main()
