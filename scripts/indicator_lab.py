#!/usr/bin/env python3
"""
Influence Radar — Indicator Lab  (반복 진화형)
────────────────────────────────────────────
실행할 때마다:
  1. 현재 지표 풀 테스트
  2. AUC < DROP_THRESHOLD 지표 자동 제거
  3. CANDIDATE_POOL 에서 무작위로 새 지표 추가 시도
  4. 추가 후 성능이 오르면 채택, 안 오르면 폐기
  5. 결과를 data/indicator_results.json 에 누적 저장

→ 실행을 반복할수록 지표 풀이 진화함.

사용:
  python scripts/indicator_lab.py           # 1회 실행 (진화 1스텝)
  python scripts/indicator_lab.py --reset   # 초기화 후 재시작
"""

import json, random, math, os, sys, copy
from datetime import datetime

RESULTS_PATH     = "data/indicator_results.json"
DROP_THRESHOLD   = 0.52   # AUC 이 이하면 제거
ADOPT_THRESHOLD  = 0.003  # 추가 후 AUC 상승 최소치
GRID_ITER        = 80_000 # 그리드서치 반복 수
N_SIGNALS        = 400    # 합성 신호 수
EQUITY_SEED      = 99     # 시뮬레이션 재현성

# ─────────────────────────────────────────────
# 지표 풀 (초기 + 후보)
# ─────────────────────────────────────────────

INITIAL_INDICATORS = {
    "hit_rate":        {"label": "과거 적중률",   "gen": lambda p: _gen_by_type(p, "hit_rate")},
    "influence_score": {"label": "영향력 점수",   "gen": lambda p: _gen_by_type(p, "influence")},
    "signal_strength": {"label": "신호 강도",     "gen": lambda _: random.betavariate(2, 2)},
    "cross_val":       {"label": "교차 검증",     "gen": lambda _: min(random.randint(0,5)/5.0, 1.0)},
    "sentiment":       {"label": "감정 분석",     "gen": lambda _: random.choices([1,0.5,0],[.5,.3,.2])[0]},
    "news_freq":       {"label": "뉴스 빈도",     "gen": lambda _: random.betavariate(1.5,3)},
    "rsi_filter":      {"label": "RSI 필터",      "gen": lambda _: float(random.choices([1,0],[.55,.45])[0])},
    "volume_surge":    {"label": "거래량 급증",   "gen": lambda _: float(random.choices([1,0],[.4,.6])[0])},
    "macd_align":      {"label": "MACD 정렬",     "gen": lambda _: float(random.choices([1,0],[.5,.5])[0])},
    "market_regime":   {"label": "시장 국면",     "gen": lambda _: float(random.choices([1,0],[.6,.4])[0])},
}

# 언제든 추가 테스트할 수 있는 후보 지표
# (실제 구현 시 real data 로 교체)
CANDIDATE_POOL = {
    "momentum_5d":     {"label": "5일 모멘텀",          "gen": lambda _: random.betavariate(2,2)},
    "sector_trend":    {"label": "섹터 추세",            "gen": lambda _: float(random.choices([1,0],[.55,.45])[0])},
    "foreign_buy":     {"label": "외국인 순매수",        "gen": lambda _: float(random.choices([1,0],[.45,.55])[0])},
    "inst_buy":        {"label": "기관 순매수",          "gen": lambda _: float(random.choices([1,0],[.5,.5])[0])},
    "bollinger_pos":   {"label": "볼린저밴드 위치",      "gen": lambda _: random.betavariate(2,2)},
    "vix_level":       {"label": "VIX 수준",             "gen": lambda _: random.betavariate(3,2)},
    "earnings_est":    {"label": "실적 전망 (Up/Down)",  "gen": lambda _: float(random.choices([1,0],[.55,.45])[0])},
    "insider_trade":   {"label": "내부자 거래",          "gen": lambda _: float(random.choices([1,0],[.35,.65])[0])},
    "options_skew":    {"label": "옵션 스큐",            "gen": lambda _: random.betavariate(2,3)},
    "short_interest":  {"label": "공매도 비율 (역)→",    "gen": lambda _: random.betavariate(2,2)},
    "pe_discount":     {"label": "PER 할인율",           "gen": lambda _: random.betavariate(2,2)},
    "revenue_growth":  {"label": "매출 성장률",          "gen": lambda _: random.betavariate(2,2)},
    "debt_ratio":      {"label": "부채비율 (역)",        "gen": lambda _: random.betavariate(1.5,3)},
    "patent_score":    {"label": "특허 출원 강도",       "gen": lambda _: random.betavariate(1.5,4)},
    "social_buzz":     {"label": "SNS 버즈량",           "gen": lambda _: random.betavariate(1.5,3)},
}

# 지표의 실제 수익 기여도 (ground truth)
# 새 지표 추가할 때 여기에도 등록 필요
TRUE_WEIGHTS = {
    "hit_rate":       0.32,
    "influence_score":0.09,
    "signal_strength":0.11,
    "cross_val":      0.09,
    "sentiment":      0.09,
    "news_freq":      0.05,
    "rsi_filter":     0.07,
    "volume_surge":   0.04,
    "macd_align":     0.03,
    "market_regime":  0.02,
    # 후보 지표 기여도
    "momentum_5d":    0.06,
    "sector_trend":   0.05,
    "foreign_buy":    0.07,
    "inst_buy":       0.06,
    "bollinger_pos":  0.04,
    "vix_level":      0.03,
    "earnings_est":   0.08,
    "insider_trade":  0.05,
    "options_skew":   0.03,
    "short_interest": 0.02,
    "pe_discount":    0.04,
    "revenue_growth": 0.05,
    "debt_ratio":     0.02,
    "patent_score":   0.01,
    "social_buzz":    0.02,
}

# ─────────────────────────────────────────────
# 합성 데이터 생성
# ─────────────────────────────────────────────

def generate_signals(n, active_indicators, seed=None):
    if seed is not None:
        random.seed(seed)

    all_defs = {**INITIAL_INDICATORS, **CANDIDATE_POOL}
    signals = []

    for i in range(n):
        ptype = random.choice(["tech_ceo","policy","finance","analyst"])
        inds  = {k: all_defs[k]["gen"](ptype) for k in active_indicators}

        # 가중합 기반 실제 확률
        total_tw = sum(TRUE_WEIGHTS.get(k,0.03) for k in active_indicators)
        score = sum((TRUE_WEIGHTS.get(k,0.03)/total_tw) * inds[k] for k in active_indicators)
        prob  = 0.30 + 0.55 * _sigmoid((score - 0.5) * 6)
        outcome = 1 if random.random() < prob else 0

        signals.append({"id":i, "outcome":outcome, "indicators": inds})

    return signals


def _gen_by_type(ptype, field):
    cfg = {
        "tech_ceo": {"hit_rate":(0.62,0.13),"influence":(0.83,0.09)},
        "policy":   {"hit_rate":(0.45,0.17),"influence":(0.76,0.10)},
        "finance":  {"hit_rate":(0.56,0.14),"influence":(0.66,0.11)},
        "analyst":  {"hit_rate":(0.59,0.11),"influence":(0.61,0.10)},
    }
    mu, sigma = cfg[ptype][field]
    return max(0.05, min(0.99, random.gauss(mu, sigma)))


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


# ─────────────────────────────────────────────
# 평가 함수
# ─────────────────────────────────────────────

def _pearson(x, y):
    n = len(x)
    if n < 2: return 0.0
    mx,my = sum(x)/n, sum(y)/n
    num = sum((xi-mx)*(yi-my) for xi,yi in zip(x,y))
    dx  = math.sqrt(sum((xi-mx)**2 for xi in x)+1e-9)
    dy  = math.sqrt(sum((yi-my)**2 for yi in y)+1e-9)
    return num/(dx*dy)

def _approx_auc(pairs):
    """(score, label) 리스트 → AUC 근사"""
    pairs = sorted(pairs, key=lambda x:-x[0])
    pos = sum(l for _,l in pairs)
    neg = len(pairs)-pos
    if pos==0 or neg==0: return 0.5
    rank_sum = sum((r+1) for r,(_, l) in enumerate(pairs) if l==1)
    return 1 - (rank_sum - pos*(pos+1)/2)/(pos*neg)

def univariate_auc(signals, indicator):
    pairs = [(s["indicators"][indicator], s["outcome"]) for s in signals]
    return _approx_auc(pairs)

def composite_score(signal, weights):
    s = sum(weights[k]*signal["indicators"][k] for k in weights)
    return _sigmoid((s-0.5)*6)

def evaluate_weights(signals, weights, threshold=0.55):
    preds = [(composite_score(s,weights), s["outcome"]) for s in signals]
    triggered = [(sc,out) for sc,out in preds if sc>=threshold]
    if not triggered:
        return {"accuracy":0,"sharpe":0,"auc":0,"triggered":0,"coverage":0}
    acc = sum(o for _,o in triggered)/len(triggered)
    cov = len(triggered)/len(preds)
    rets = [0.07 if o else -0.03 for _,o in triggered]
    avg_r = sum(rets)/len(rets)
    std_r = math.sqrt(sum((r-avg_r)**2 for r in rets)/len(rets)+1e-9)
    sharpe = avg_r/std_r
    auc = _approx_auc(sorted(preds,key=lambda x:-x[0]))
    return {"accuracy":round(acc*100,2),"sharpe":round(sharpe,4),
            "auc":round(auc,4),"triggered":len(triggered),"coverage":round(cov*100,2)}


# ─────────────────────────────────────────────
# 랜덤 그리드 서치
# ─────────────────────────────────────────────

def grid_search(signals, active_indicators, n_iter=GRID_ITER):
    best_obj  = -9999
    best_w    = None
    best_m    = None
    keys      = list(active_indicators)

    for _ in range(n_iter):
        raw   = [random.random() for _ in keys]
        total = sum(raw)+1e-9
        w     = {k: raw[i]/total for i,k in enumerate(keys)}
        m     = evaluate_weights(signals, w)
        obj   = m["sharpe"] * m["auc"] * (m["coverage"]/100+0.1)
        if obj > best_obj:
            best_obj = obj
            best_w   = {k: round(v,4) for k,v in w.items()}
            best_m   = m

    return best_w, best_m


# ─────────────────────────────────────────────
# 수익 시뮬레이션
# ─────────────────────────────────────────────

def equity_sim(signals, weights, threshold=0.55):
    rng = random.Random(EQUITY_SEED)
    sh  = signals[:]
    rng.shuffle(sh)
    eq  = [100.0]
    for s in sh:
        if composite_score(s, weights) >= threshold:
            r = 0.07 if s["outcome"] else -0.03
            eq.append(round(eq[-1]*(1+r), 2))
    return eq


# ─────────────────────────────────────────────
# 지표 진화 루프 (핵심)
# ─────────────────────────────────────────────

def evolve_indicators(prev_state):
    """
    prev_state: 이전 실행 결과 dict (없으면 None)
    Returns: new_state dict
    """
    all_defs = {**INITIAL_INDICATORS, **CANDIDATE_POOL}

    # 초기 상태
    if prev_state is None:
        active = set(INITIAL_INDICATORS.keys())
        history = []
        generation = 1
    else:
        active     = set(prev_state["active_indicators"])
        history    = prev_state.get("history", [])
        generation = prev_state.get("generation", 1) + 1

    print(f"\n{'='*60}")
    print(f"📊 INDICATOR LAB — Generation {generation}")
    print(f"{'='*60}")
    print(f"현재 활성 지표 ({len(active)}개): {', '.join(all_defs[k]['label'] for k in sorted(active))}")

    # ── 신호 생성
    signals = generate_signals(N_SIGNALS, active)
    pos = sum(s["outcome"] for s in signals)
    print(f"\n신호 {N_SIGNALS}건  수익률 {pos/N_SIGNALS*100:.1f}%\n")

    # ── 단변량 AUC
    uni = {}
    print(f"  {'지표':<22} {'AUC':>7}  {'판정'}")
    print(f"  {'─'*45}")
    dropped = []
    for k in sorted(active):
        auc  = univariate_auc(signals, k)
        keep = auc >= DROP_THRESHOLD
        mark = "✅ 유지" if keep else "❌ 제거"
        print(f"  {all_defs[k]['label']:<22} {auc:.4f}  {mark}")
        uni[k] = auc
        if not keep:
            dropped.append(k)

    if dropped:
        print(f"\n  → 제거: {', '.join(all_defs[k]['label'] for k in dropped)}")
        active -= set(dropped)

    # ── 기존 활성 지표로 그리드서치
    print(f"\n[그리드서치] 현재 {len(active)}개 지표 최적화...")
    base_signals = generate_signals(N_SIGNALS, active, seed=1)
    base_w, base_m = grid_search(base_signals, active)
    print(f"  기준 성능  정확도 {base_m['accuracy']}%  AUC {base_m['auc']}  Sharpe {base_m['sharpe']:.3f}")

    # ── 후보 지표 추가 테스트
    candidates_left = [k for k in CANDIDATE_POOL if k not in active]
    random.shuffle(candidates_left)
    added = []

    for cand in candidates_left[:4]:  # 한 번에 최대 4개 시도
        trial_active = active | {cand}
        trial_signals = generate_signals(N_SIGNALS, trial_active, seed=1)
        trial_w, trial_m = grid_search(trial_signals, trial_active, n_iter=30_000)
        delta_auc = trial_m["auc"] - base_m["auc"]

        label = all_defs[cand]["label"]
        if delta_auc >= ADOPT_THRESHOLD:
            active.add(cand)
            base_m = trial_m
            base_w = trial_w
            print(f"  ✅ 채택: {label}  (+AUC {delta_auc:+.4f})")
            added.append(cand)
        else:
            print(f"  ⬜ 기각: {label}  (ΔAUC {delta_auc:+.4f}  < {ADOPT_THRESHOLD})")

    # ── 최종 그리드서치
    print(f"\n[최종 최적화] {len(active)}개 지표...")
    final_signals = generate_signals(N_SIGNALS, active)
    final_w, final_m = grid_search(final_signals, active)

    # ── 수익 시뮬레이션
    eq = equity_sim(final_signals, final_w)
    eq_equal = equity_sim(final_signals, {k: 1/len(active) for k in active})

    # ── 상관 행렬
    corr = {}
    for a in sorted(active):
        corr[a] = {}
        va = [s["indicators"][a] for s in final_signals]
        for b in sorted(active):
            vb = [s["indicators"][b] for s in final_signals]
            corr[a][b] = round(_pearson(va, vb), 3)

    # ── 히스토리 기록
    history.append({
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "active_count": len(active),
        "dropped": dropped,
        "added": added,
        "accuracy": final_m["accuracy"],
        "auc": final_m["auc"],
        "sharpe": final_m["sharpe"],
    })

    # ── 최종 결과 출력
    print(f"\n{'='*60}")
    print(f"🎯 Generation {generation} 결과")
    print(f"  활성 지표: {len(active)}개")
    print(f"  정확도:    {final_m['accuracy']}%")
    print(f"  AUC:       {final_m['auc']}")
    print(f"  Sharpe:    {final_m['sharpe']:.3f}")
    print(f"  수익 곡선: 100 → {eq[-1]:.1f}  (균등: {eq_equal[-1]:.1f})")
    print(f"\n  최적 가중치 (상위 5개):")
    for k, v in sorted(final_w.items(), key=lambda x:-x[1])[:5]:
        bar = "█" * int(v * 30)
        print(f"    {all_defs[k]['label']:<20} {v:.4f}  {bar}")

    state = {
        "generated_at": datetime.now().isoformat(),
        "generation": generation,
        "active_indicators": sorted(list(active)),
        "indicator_labels": {k: all_defs[k]["label"] for k in active},
        "univariate_auc": {k: round(univariate_auc(final_signals, k), 4) for k in active},
        "optimal_weights": final_w,
        "optimal_metrics": final_m,
        "correlation_matrix": corr,
        "equity_optimal": eq[:200],
        "equity_equal": eq_equal[:200],
        "history": history,
    }

    return state


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main():
    reset = "--reset" in sys.argv

    prev_state = None
    if not reset and os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            prev_state = json.load(f)
        print(f"이전 결과 로드  Generation {prev_state.get('generation',1)}  AUC {prev_state.get('optimal_metrics',{}).get('auc','-')}")
    else:
        print("초기 상태로 시작")

    new_state = evolve_indicators(prev_state)

    os.makedirs("data", exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)

    print(f"\n💾 저장 완료: {RESULTS_PATH}")
    print("다시 실행하면 지표 풀이 진화합니다: python scripts/indicator_lab.py")


if __name__ == "__main__":
    main()
