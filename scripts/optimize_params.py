#!/usr/bin/env python3
"""
Influence Radar — 파라미터 최적화 (Phase 2)
════════════════════════════════════════════════════════════
지표의 "설정값"까지 자동 최적화.
기존: RSI=14, MACD=12/26/9 고정
이후: 실데이터 기반으로 최적 파라미터 탐색

알고리즘:
  1. 각 이벤트의 OHLCV 데이터 re-fetch
  2. N=500 랜덤 파라미터 조합으로 AUC 계산
  3. 상위 20개 조합 scipy 정밀 최적화
  4. data/optimal_params.json 저장

자동 실행: .github/workflows/param-optimizer.yml (월 1회)
"""

import json, os, random, math
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

try:
    from scipy.optimize import minimize
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

TRAINING_PATH  = "data/training_data.json"
PARAMS_PATH    = "data/optimal_params.json"
RANDOM_TRIALS  = 500     # 랜덤 탐색 횟수
TOP_K          = 20      # scipy 정밀 최적화 후보 수
HOLD_DAYS      = 10      # 수익 판단 기간
TARGET_RET     = 0.03    # 수익 기준 (3%)

# ──────────────────────────────────────────────────────────────
# 파라미터 탐색 공간
# ──────────────────────────────────────────────────────────────
PARAM_SPACE = {
    "rsi_period":    (7,  25),    # RSI 계산 기간
    "macd_fast":     (8,  16),    # MACD 단기 EMA
    "macd_slow":     (20, 32),    # MACD 장기 EMA
    "macd_signal":   (7,  13),    # MACD 시그널 EMA
    "bb_period":     (14, 26),    # 볼린저밴드 기간
    "bb_std":        (1.5, 2.5),  # 볼린저밴드 표준편차 배수
    "volume_ma":     (10, 30),    # 거래량 이동평균 기간
    "momentum_days": (3,  12),    # 모멘텀 계산 일수
    "atr_period":    (10, 21),    # ATR 계산 기간
    "trend_period":  (10, 30),    # 추세 계산 기간
    "rsi_low":       (25, 35),    # RSI 매수 하한
    "rsi_high":      (60, 75),    # RSI 매수 상한
}

DEFAULT_PARAMS = {
    "rsi_period": 14, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
    "bb_period": 20, "bb_std": 2.0, "volume_ma": 20, "momentum_days": 5,
    "atr_period": 14, "trend_period": 20, "rsi_low": 28, "rsi_high": 65,
}

# ──────────────────────────────────────────────────────────────
# 파라미터 기반 지표 계산
# ──────────────────────────────────────────────────────────────

def calc_indicators_with_params(df, params):
    """파라미터를 받아 모든 지표 계산. 실패 시 None 반환."""
    try:
        close  = df['Close']
        high   = df['High']
        low    = df['Low']
        volume = df['Volume']
        n = len(close)

        rp   = int(params["rsi_period"])
        mf   = int(params["macd_fast"])
        ms   = int(params["macd_slow"])
        msig = int(params["macd_signal"])
        bbp  = int(params["bb_period"])
        bbs  = float(params["bb_std"])
        vma  = int(params["volume_ma"])
        md   = int(params["momentum_days"])
        ap   = int(params["atr_period"])
        tp   = int(params["trend_period"])
        rl   = float(params["rsi_low"])
        rh   = float(params["rsi_high"])

        min_len = max(ms + msig, bbp, vma, tp) + 5
        if n < min_len:
            return None

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(rp).mean()
        loss = (-delta.clip(upper=0)).rolling(rp).mean()
        rs  = gain / (loss + 1e-9)
        rsi = (100 - 100 / (1 + rs)).iloc[-1]
        rsi_filter = 1.0 if rl <= rsi <= rh else 0.0

        # MACD
        ema_f = close.ewm(span=mf, adjust=False).mean()
        ema_s = close.ewm(span=ms, adjust=False).mean()
        macd  = ema_f - ema_s
        sig   = macd.ewm(span=msig, adjust=False).mean()
        macd_align = 1.0 if macd.iloc[-1] > 0 else 0.0

        # Bollinger
        bma  = close.rolling(bbp).mean()
        bstd = close.rolling(bbp).std()
        upper = bma + bbs * bstd
        lower = bma - bbs * bstd
        boll = float(np.clip(
            (close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-9), 0, 1))

        # Volume
        avg_vol = volume.rolling(vma).mean().iloc[-1]
        vol_ratio = float(min(volume.iloc[-1] / (avg_vol + 1), 5.0) / 5.0) if avg_vol > 0 else 0.5
        vol_surge = 1.0 if volume.iloc[-1] > avg_vol * 1.5 else 0.0

        # Momentum
        if n > md + 1:
            ret = (close.iloc[-1] - close.iloc[-(md+1)]) / (close.iloc[-(md+1)] + 1e-9)
            mom = float(np.clip(0.5 + ret * 5, 0, 1))
        else:
            mom = 0.5

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(ap).mean().iloc[-1]
        atr_stab = float(np.clip(1 - (atr / (close.iloc[-1] + 1e-9)) * 10, 0, 1))

        # Trend
        if n >= tp:
            y = close.values[-tp:]
            x = np.arange(tp)
            slope = np.polyfit(x, y, 1)[0]
            trend = 1.0 if slope > 0 else 0.0
        else:
            trend = 0.5

        # 52주 위치
        high_52w = close.rolling(min(n, 252)).max().iloc[-1]
        vs_52w = float(np.clip(close.iloc[-1] / (high_52w + 1e-9), 0, 1))

        return {
            "rsi_filter": rsi_filter, "macd_align": macd_align,
            "bollinger_pos": boll, "volume_ratio": vol_ratio,
            "volume_surge": vol_surge, "momentum_5d": mom,
            "atr_stability": atr_stab, "trend_dir_20": trend,
            "price_vs_52w": vs_52w,
        }
    except Exception:
        return None


def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def composite_score(inds, weights=None):
    """균등 가중치로 복합 점수 계산"""
    if not inds:
        return 0.5
    keys = list(inds.keys())
    if weights:
        s = sum(weights.get(k, 1/len(keys)) * inds[k] for k in keys)
    else:
        s = sum(inds[k] for k in keys) / len(keys)
    return sigmoid((s - 0.5) * 8)

def calc_auc(scores_outcomes):
    """AUC 계산"""
    pos = [s for s, o in scores_outcomes if o]
    neg = [s for s, o in scores_outcomes if not o]
    if not pos or not neg:
        return 0.5
    total = len(pos) * len(neg)
    wins  = sum(1 for p in pos for n in neg if p > n)
    ties  = sum(1 for p in pos for n in neg if p == n)
    return (wins + 0.5 * ties) / total


# ──────────────────────────────────────────────────────────────
# 이벤트 데이터 re-fetch
# ──────────────────────────────────────────────────────────────

def fetch_event_data(events):
    """각 이벤트의 OHLCV 데이터 수집. 캐시 활용."""
    print(f"📥 이벤트 OHLCV 수집 중 ({len(events)}건)...")
    cache = {}
    results = []

    for i, ev in enumerate(events):
        date_str, person, symbol = ev["date"], ev["person"], ev["symbol"]
        outcome = ev.get("outcome", False)

        try:
            dt  = datetime.strptime(date_str, "%Y-%m-%d")
            s   = (dt - timedelta(days=120)).strftime("%Y-%m-%d")
            e   = (dt + timedelta(days=HOLD_DAYS + 5)).strftime("%Y-%m-%d")

            cache_key = f"{symbol}_{s}_{e}"
            if cache_key not in cache:
                df = yf.Ticker(symbol).history(start=s, end=e, auto_adjust=True)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                cache[cache_key] = df

            df = cache[cache_key]
            if df.empty or len(df) < 30:
                continue

            # 이벤트 날짜 위치 찾기
            dates = df.index.normalize()
            ev_dt = pd.Timestamp(date_str)
            pos_arr = np.where(dates >= ev_dt)[0]
            if len(pos_arr) == 0:
                continue
            pos = pos_arr[0]
            if pos < 20:
                continue

            df_pre = df.iloc[:pos+1].copy()
            results.append({
                "symbol": symbol,
                "date": date_str,
                "df": df_pre,
                "outcome": outcome,
            })

            if (i+1) % 20 == 0:
                print(f"  {i+1}/{len(events)} 완료...")

        except Exception as ex:
            pass

    print(f"✅ {len(results)}건 수집 완료")
    return results


# ──────────────────────────────────────────────────────────────
# 파라미터 평가
# ──────────────────────────="────────────────────────────────
# ──────────────────────────────────────────────────────────────

def evaluate_params(params, event_data):
    """파라미터 조합에 대한 AUC 계산"""
    scores_outcomes = []
    for ev in event_data:
        inds = calc_indicators_with_params(ev["df"], params)
        if inds is None:
            continue
        score = composite_score(inds)
        scores_outcomes.append((score, ev["outcome"]))
    if len(scores_outcomes) < 10:
        return 0.5
    return calc_auc(scores_outcomes)


def random_params():
    """랜덤 파라미터 생성"""
    p = {}
    for k, (lo, hi) in PARAM_SPACE.items():
        if isinstance(lo, int) and isinstance(hi, int):
            p[k] = random.randint(lo, hi)
        else:
            p[k] = round(random.uniform(lo, hi), 2)
    # macd_fast < macd_slow 보장
    if p["macd_fast"] >= p["macd_slow"]:
        p["macd_slow"] = p["macd_fast"] + random.randint(8, 14)
        p["macd_slow"] = min(p["macd_slow"], int(PARAM_SPACE["macd_slow"][1]))
    # rsi_low < rsi_high 보장
    if p["rsi_low"] >= p["rsi_high"]:
        p["rsi_high"] = p["rsi_low"] + random.randint(20, 30)
        p["rsi_high"] = min(p["rsi_high"], int(PARAM_SPACE["rsi_high"][1]))
    return p


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("🔬 파라미터 최적화 — Phase 2")
    print("=" * 65)

    # 이전 결과 로드
    prev_best_auc = 0.0
    prev_params   = DEFAULT_PARAMS.copy()
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH) as f:
            prev = json.load(f)
        prev_best_auc = prev.get("best_auc", 0)
        prev_params   = prev.get("best_params", DEFAULT_PARAMS)
        print(f"이전 최고 AUC: {prev_best_auc:.4f}")

    # 훈련 데이터 로드
    if not os.path.exists(TRAINING_PATH):
        print("❌ training_data.json 없음. build_training_data.py 먼저 실행.")
        return
    with open(TRAINING_PATH) as f:
        td = json.load(f)
    events = td.get("signals", [])
    if len(events) < 20:
        print(f"❌ 이벤트 {len(events)}건 — 최소 20건 필요")
        return
    print(f"훈련 이벤트: {len(events)}건\n")

    # OHLCV 수집
    event_data = fetch_event_data(events)
    if len(event_data) < 15:
        print("❌ 유효 이벤트 부족")
        return

    # Phase 1: 랜덤 탐색
    print(f"\n🎲 Phase 1: 랜덤 탐색 {RANDOM_TRIALS}회...")
    candidates = []

    # 기본값 포함
    base_auc = evaluate_params(DEFAULT_PARAMS, event_data)
    candidates.append((base_auc, DEFAULT_PARAMS.copy()))
    print(f"  기본값 AUC: {base_auc:.4f}")

    # 이전 최고값 포함
    if prev_params != DEFAULT_PARAMS:
        prev_auc = evaluate_params(prev_params, event_data)
        candidates.append((prev_auc, prev_params.copy()))
        print(f"  이전 최고 AUC: {prev_auc:.4f}")

    for i in range(RANDOM_TRIALS):
        p = random_params()
        auc = evaluate_params(p, event_data)
        candidates.append((auc, p))
        if (i+1) % 100 == 0:
            best_so_far = max(c[0] for c in candidates)
            print(f"  {i+1}/{RANDOM_TRIALS} 완료  현재 최고: {best_so_far:.4f}")

    candidates.sort(key=lambda x: -x[0])
    top_candidates = candidates[:TOP_K]
    print(f"\n상위 {TOP_K}개 AUC 범위: {top_candidates[-1][0]:.4f} ~ {top_candidates[0][0]:.4f}")

    # Phase 2: scipy 정밀 최적화
    best_auc    = top_candidates[0][0]
    best_params = top_candidates[0][1].copy()

    if HAS_SCIPY:
        print(f"\n🔬 Phase 2: scipy 정밀 최적화 ({TOP_K}개 후보)...")
        param_keys = list(PARAM_SPACE.keys())

        for rank, (_, init_p) in enumerate(top_candidates[:5]):
            x0 = [float(init_p[k]) for k in param_keys]
            bounds = [(PARAM_SPACE[k][0], PARAM_SPACE[k][1]) for k in param_keys]

            def objective(x):
                p = {}
                for i2, k in enumerate(param_keys):
                    lo, hi = PARAM_SPACE[k]
                    v = max(lo, min(hi, x[i2]))
                    p[k] = int(round(v)) if isinstance(lo, int) else round(v, 2)
                # 유효성 보장
                if p.get("macd_fast", 12) >= p.get("macd_slow", 26):
                    return 1.0
                if p.get("rsi_low", 28) >= p.get("rsi_high", 65):
                    return 1.0
                auc = evaluate_params(p, event_data)
                return -auc  # 최소화

            res = minimize(objective, x0, method='Nelder-Mead',
                          options={'maxiter': 500, 'xatol': 0.5, 'fatol': 0.001})
            refined_p = {}
            for i2, k in enumerate(param_keys):
                lo, hi = PARAM_SPACE[k]
                v = max(lo, min(hi, res.x[i2]))
                refined_p[k] = int(round(v)) if isinstance(lo, int) else round(v, 2)

            refined_auc = evaluate_params(refined_p, event_data)
            print(f"  후보 {rank+1}: {-res.fun:.4f} → 검증 {refined_auc:.4f}")

            if refined_auc > best_auc:
                best_auc    = refined_auc
                best_params = refined_p.copy()

    # 결과 저장
    improved = best_auc > prev_best_auc
    print(f"\n{'='*65}")
    print(f"{'🏆 개선!' if improved else '📊 변동 없음'}")
    print(f"  이전 최고: {prev_best_auc:.4f}")
    print(f"  현재 결과: {best_auc:.4f} {'(+' + str(round(best_auc-prev_best_auc,4)) + ')' if improved else ''}")

    print(f"\n최적 파라미터:")
    for k, v in best_params.items():
        default_v = DEFAULT_PARAMS.get(k)
        tag = f"  ← 기본값 {default_v}" if v != default_v else ""
        print(f"  {k:<20}: {v}{tag}")

    output = {
        "updated_at": datetime.now().isoformat(),
        "best_auc":   round(best_auc, 4),
        "best_params": best_params,
        "default_params": DEFAULT_PARAMS,
        "improved": improved,
        "event_count": len(event_data),
        "trials": RANDOM_TRIALS,
    }
    os.makedirs("data", exist_ok=True)
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 저장: {PARAMS_PATH}")

if __name__ == "__main__":
    main()
