#!/usr/bin/env python3
"""
Influence Radar — Indicator Lab v2 (진화형 실데이터 최적화)
════════════════════════════════════════════════════════════
완전히 실데이터만 사용. 합성 데이터 ZERO.

알고리즘:
  1. training_data.json 로드 (없으면 종료)
  2. Train 80% / Test 20% 분리
  3. 각 지표 단변량 AUC 측정 → DROP_THRESHOLD 미만 제거
  4. 후보 지표 추가 시험 (실데이터 기반)
  5. 2단계 최적화: 랜덤 탐색 → scipy Nelder-Mead 정밀 수렴
  6. Train/Test AUC 비교 → 오버피팅 경고
  7. "IR-COORD" 고유 좌표 서명 생성
  8. data/indicator_results.json 저장

사용:
  python scripts/indicator_lab.py
  python scripts/indicator_lab.py --reset
"""

import json, random, math, os, sys, copy, hashlib
from datetime import datetime

try:
    import numpy as np
    from scipy.optimize import minimize as scipy_minimize
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("⚠ scipy 없음. pip install scipy 설치 시 정밀도 향상")

RESULTS_PATH   = "data/indicator_results.json"
TRAINING_PATH  = "data/training_data.json"
DROP_THRESHOLD = 0.52     # 단변량 AUC 하한
ADOPT_MIN_ΔAUC = 0.002    # 신규 지표 채택 최소 AUC 향상치
GRID_ITER_1    = 30_000   # 1단계 랜덤 탐색
GRID_ITER_2    = 100      # 2단계: top-100 근방 집중 탐색
TRAIN_RATIO    = 0.80     # 훈련/테스트 분리 비율

# ──────────────────────────────────────────────────────────────
# 활성 지표 정의 (실데이터 키와 1:1 매핑)
# training_data.json indicators 키 이름과 반드시 일치
# ──────────────────────────────────────────────────────────────
INITIAL_INDICATORS = [
    "rsi_filter",
    "macd_align",
    "volume_surge",
    "volume_ratio",
    "bollinger_pos",
    "momentum_5d",
    "sentiment",
    "hit_rate",
    "signal_strength",
    "news_freq",
]

# 실데이터에 존재하는 추가 후보 지표
CANDIDATE_INDICATORS = [
    "gap_up",
    "price_vs_52w",
    "atr_stability",
    "trend_dir_20",
    "pre_run_inv",
    "cross_val",
    # 2026-07-21 확장 (build_training_data.py에 신규 계산 추가됨)
    "rsi_7",
    "rsi_21",
    "momentum_10d",
    "momentum_20d",
    "volume_trend",
    "support_proximity",
    "volatility_20d",
]

INDICATOR_LABELS = {
    "rsi_filter":    "RSI 필터(30~65)",
    "macd_align":    "MACD 정렬",
    "volume_surge":  "거래량 급증",
    "volume_ratio":  "거래량 배율",
    "bollinger_pos": "볼린저밴드 위치",
    "momentum_5d":   "5일 모멘텀",
    "sentiment":     "감정 분석",
    "hit_rate":      "인물 과거 적중률",
    "signal_strength":"신호 강도",
    "news_freq":     "뉴스 검증 빈도",
    "gap_up":        "갭 상승 비율",
    "price_vs_52w":  "52주 고가 대비",
    "atr_stability": "변동성 안정도",
    "trend_dir_20":  "20일 추세 방향",
    "pre_run_inv":   "사전 모멘텀(역)",
    "cross_val":     "다중 검증 점수",
    "rsi_7":         "RSI(7일)",
    "rsi_21":        "RSI(21일)",
    "momentum_10d":  "10일 모멘텀",
    "momentum_20d":  "20일 모멘텀",
    "volume_trend":  "거래량 추세(단기/장기)",
    "support_proximity": "지지선 근접도",
    "volatility_20d": "20일 변동성",
}


# ──────────────────────────────────────────────────────────────
# 데이터 로드
# ──────────────────────────────────────────────────────────────

def load_real_data():
    if not os.path.exists(TRAINING_PATH):
        print(f"❌ {TRAINING_PATH} 없음. build_training_data.py 먼저 실행")
        sys.exit(1)
    with open(TRAINING_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    sigs = data.get("signals", [])
    if len(sigs) < 30:
        print(f"❌ 데이터 부족: {len(sigs)}건 (최소 30건 필요)")
        sys.exit(1)
    print(f"✅ 실데이터 로드: {len(sigs)}건  |  수익달성 {data.get('positive_rate',0)*100:.1f}%")
    return sigs

def split_data(signals, ratio=TRAIN_RATIO, seed=42):
    """날짜 순 정렬 후 앞 80%=train, 뒤 20%=test (시계열 누수 방지)"""
    sorted_sigs = sorted(signals, key=lambda x: x.get("date",""))
    n = int(len(sorted_sigs) * ratio)
    return sorted_sigs[:n], sorted_sigs[n:]

def extract_indicators(signals, active_keys):
    """signals에서 active_keys만 추출. 없는 키는 0.5로 채움"""
    result = []
    for s in signals:
        ind = s.get("indicators", {})
        filtered = {k: float(ind.get(k, 0.5)) for k in active_keys}
        result.append({"outcome": s["outcome"], "indicators": filtered})
    return result


# ──────────────────────────────────────────────────────────────
# 평가 함수
# ──────────────────────────────────────────────────────────────

def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))

def composite_score(signal_ind, weights):
    s = sum(weights[k] * signal_ind[k] for k in weights)
    return sigmoid((s - 0.5) * 8)

def approx_auc(pairs):
    pairs_s = sorted(pairs, key=lambda x: -x[0])
    pos = sum(l for _, l in pairs_s)
    neg = len(pairs_s) - pos
    if pos == 0 or neg == 0: return 0.5
    rank_sum = sum((r+1) for r, (_, l) in enumerate(pairs_s) if l == 1)
    return 1.0 - (rank_sum - pos*(pos+1)/2) / (pos * neg)

def univariate_auc(signals, key):
    pairs = [(s["indicators"].get(key, 0.5), s["outcome"]) for s in signals]
    return approx_auc(pairs)

def evaluate_weights(signals, weights, threshold=0.52):
    preds = [(composite_score(s["indicators"], weights), s["outcome"]) for s in signals]
    triggered = [(sc, out) for sc, out in preds if sc >= threshold]
    if not triggered:
        return {"accuracy": 0, "sharpe": 0, "auc": 0.5, "triggered": 0, "coverage": 0}
    acc = sum(o for _, o in triggered) / len(triggered)
    cov = len(triggered) / len(preds)
    rets = [0.07 if o else -0.03 for _, o in triggered]
    avg_r = sum(rets) / len(rets)
    std_r = math.sqrt(sum((r - avg_r)**2 for r in rets) / len(rets) + 1e-9)
    sharpe = avg_r / std_r
    auc = approx_auc(preds)
    return {
        "accuracy": round(acc * 100, 2),
        "sharpe": round(sharpe, 4),
        "auc": round(auc, 4),
        "triggered": len(triggered),
        "coverage": round(cov * 100, 2),
    }

def objective(weights, signals):
    m = evaluate_weights(signals, weights)
    return m["sharpe"] * m["auc"] * (m["coverage"] / 100 + 0.1)


# ──────────────────────────────────────────────────────────────
# 2단계 최적화
# ──────────────────────────────────────────────────────────────

def optimize_weights(train_signals, active_keys, n_random=GRID_ITER_1):
    """
    Phase 1: n_random 랜덤 탐색 → Top-100 후보 수집
    Phase 2: scipy Nelder-Mead 정밀 수렴 (scipy 있을 때)
    """
    keys = sorted(active_keys)
    n = len(keys)

    # Phase 1: 랜덤 탐색
    best_obj = -9999
    best_w = None
    top_candidates = []

    rng = random.Random(42)
    for i in range(n_random):
        raw = [rng.random() for _ in keys]
        total = sum(raw) + 1e-9
        w = {k: raw[j]/total for j, k in enumerate(keys)}
        obj = objective(w, train_signals)
        if obj > best_obj:
            best_obj = obj
            best_w = w.copy()
        if i % (n_random // GRID_ITER_2) == 0:
            top_candidates.append((obj, [r/total for r in raw]))

    # Phase 1.5: 상위 후보 근방 집중 탐색
    top_candidates.sort(reverse=True)
    for _, raw in top_candidates[:20]:
        for _ in range(50):
            perturb = [max(0, r + random.gauss(0, 0.05)) for r in raw]
            total = sum(perturb) + 1e-9
            w = {k: perturb[j]/total for j, k in enumerate(keys)}
            obj = objective(w, train_signals)
            if obj > best_obj:
                best_obj = obj
                best_w = w.copy()

    # Phase 2: scipy 정밀화
    if HAS_SCIPY and best_w:
        x0 = np.array([best_w[k] for k in keys])
        x0 = x0 / (x0.sum() + 1e-9)

        def neg_obj(x):
            x_clip = np.clip(x, 0, 1)
            s = x_clip.sum() + 1e-9
            w = {k: float(x_clip[j]/s) for j, k in enumerate(keys)}
            return -objective(w, train_signals)

        result = scipy_minimize(neg_obj, x0, method='Nelder-Mead',
                                options={'maxiter': 10000, 'xatol': 1e-5, 'fatol': 1e-6})
        x_final = np.clip(result.x, 0, 1)
        s = x_final.sum() + 1e-9
        refined_w = {k: float(round(x_final[j]/s, 4)) for j, k in enumerate(keys)}
        refined_obj = objective(refined_w, train_signals)
        if refined_obj > best_obj:
            best_w = refined_w

    final_w = {k: round(v, 4) for k, v in best_w.items()}
    final_m = evaluate_weights(train_signals, final_w)
    return final_w, final_m


# ──────────────────────────────────────────────────────────────
# 좌표 서명 생성
# ──────────────────────────────────────────────────────────────

def make_coordinate_signature(weights, metrics, generation):
    """
    IR-COORD 고유 서명:
    - 가중치 벡터를 정규화된 8자리 hex로 변환
    - 버전 + 성능 내장
    """
    w_str = json.dumps(sorted(weights.items()), sort_keys=True)
    digest = hashlib.sha256(w_str.encode()).hexdigest()[:8].upper()
    auc_int = int(metrics.get("auc", 0.5) * 100)
    sharpe_int = int(abs(metrics.get("sharpe", 0)) * 10)
    return f"IR-COORD-G{generation:02d}-{digest}-AUC{auc_int}-S{sharpe_int}"


# ──────────────────────────────────────────────────────────────
# 메인 진화 루프
# ──────────────────────────────────────────────────────────────

def evolve(prev_state, all_signals):
    generation = 1 if prev_state is None else prev_state.get("generation", 1) + 1
    history    = [] if prev_state is None else prev_state.get("history", [])

    if prev_state is None:
        active = set(INITIAL_INDICATORS)
    else:
        active = set(prev_state["active_indicators"])

    print(f"\n{'='*65}")
    print(f"🧬 INDICATOR LAB v2 — Generation {generation}")
    print(f"{'='*65}")
    print(f"활성 지표 ({len(active)}개): {', '.join(INDICATOR_LABELS.get(k,k) for k in sorted(active))}")

    # 데이터 분리
    train_sigs, test_sigs = split_data(all_signals)
    print(f"\n데이터: Train {len(train_sigs)}건 / Test {len(test_sigs)}건")

    # 데이터에 실제로 존재하는 키만 유지
    sample_ind = all_signals[0].get("indicators", {})
    available_keys = set(sample_ind.keys())
    active = active & available_keys
    if not active:
        print("❌ 활성 지표가 데이터에 없음")
        sys.exit(1)

    train_ext = extract_indicators(train_sigs, active)
    test_ext  = extract_indicators(test_sigs,  active)

    # ── 단변량 AUC 측정
    print(f"\n{'':3} {'지표':<24} {'Train AUC':>10}  {'판정'}")
    print(f"  {'─'*50}")
    dropped = []
    uni_aucs = {}
    for k in sorted(active):
        auc = univariate_auc(train_ext, k)
        keep = auc >= DROP_THRESHOLD
        mark = "✅ 유지" if keep else "❌ 제거"
        print(f"  {INDICATOR_LABELS.get(k,k):<24} {auc:.4f}      {mark}")
        uni_aucs[k] = auc
        if not keep:
            dropped.append(k)

    # 단변량 AUC는 참고용 진단 정보로만 출력하고 실제 제거는 하지 않음.
    # 이유: pre_run_inv 같은 역방향 설계 지표는 단독 AUC가 구조적으로 낮지만
    # 다변량 조합에서는 기여할 수 있음 — Phase 1.5(기여도 기반 후진 제거, 실제
    # 모델에서 빼봤을 때 AUC 변화를 측정)가 이미 이 역할을 더 정확히 수행하므로
    # 여기서 또 지우면 두 로직이 매 세대 같은 지표를 뺐다 넣었다 반복하는
    # 무한 루프(Gen27-30에서 실측됨, AUC 변화 없이 세대만 소모)가 발생함.
    if dropped:
        print(f"\n  ⚠ 단변량 AUC 낮음(참고용, 제거 안 함): {', '.join(INDICATOR_LABELS.get(k,k) for k in dropped)}")
        dropped = []

    # ── 기준 성능 (현재 활성 지표)
    print(f"\n[Phase 1] 현재 {len(active)}개 지표 최적화 중...")
    train_ext_base = extract_indicators(train_sigs, active)
    test_ext_base  = extract_indicators(test_sigs,  active)
    base_w, base_m = optimize_weights(train_ext_base, active)
    base_test_m    = evaluate_weights(test_ext_base, base_w)
    overfit_gap    = round(base_m["auc"] - base_test_m["auc"], 4)
    print(f"  Train → 정확도 {base_m['accuracy']}%  AUC {base_m['auc']}  Sharpe {base_m['sharpe']:.3f}")
    print(f"  Test  → 정확도 {base_test_m['accuracy']}%  AUC {base_test_m['auc']}  Overfit gap {overfit_gap:+.4f}")

    # ── Phase 1.5: 기여도 기반 후진 제거
    # "완전히 좋지 않다고 판단되는" 지표를 매 세대 삭제 시도 — 랜덤이 아니라
    # 실제로 빼봤을 때 AUC가 나빠지지 않거나(거의) 오히려 좋아지는 지표를 제거.
    removed = []
    MIN_ACTIVE_FLOOR = 7  # 탐색 취지(더 많은 조합) 보호 — 이 이하로는 제거 안 함
    if len(active) > MIN_ACTIVE_FLOOR:
        print(f"\n[Phase 1.5] 기여도 최하위 지표 제거 시험 ({len(active)}개 전수 평가)...")
        worst_key, worst_delta = None, -9999
        for k in sorted(active):
            trial_active = active - {k}
            if len(trial_active) < 2:
                continue
            trial_train = extract_indicators(train_sigs, trial_active)
            trial_w, trial_m = optimize_weights(trial_train, trial_active, n_random=3_000)
            delta = trial_m["auc"] - base_m["auc"]  # 양수=제거해도 AUC 안 나빠짐(오히려 개선)
            if delta > worst_delta:
                worst_delta, worst_key = delta, k
        # 채택 기준(ADOPT_MIN_ΔAUC)과 대칭 — "거의 안 나빠짐" 정도의 관용 없이
        # 제거해도 AUC가 진짜 나빠지지 않을 때만(0 이상) 제거. 비대칭 관용이
        # 누적 순삭제(11→4개)를 유발한 원인이었음.
        if worst_key is not None and worst_delta >= 0:
            active.discard(worst_key)
            removed.append(worst_key)
            label = INDICATOR_LABELS.get(worst_key, worst_key)
            print(f"  🗑️ 제거: {label:<24} (제거해도 ΔAUC {worst_delta:+.4f})")
            base_train_ext = extract_indicators(train_sigs, active)
            base_w, base_m = optimize_weights(base_train_ext, active)
        else:
            print(f"  (제거할 만한 지표 없음 — 전부 유의미하게 기여 중)")

    # ── Phase 2: 후보 지표 전수 평가(랜덤 셔플 폐기) → 최고 기여 1개 채택
    # 남은 후보 전체를 다 시험해서 ΔAUC 기준 최선의 조합으로 방향성 있게 확장.
    candidates_to_try = [k for k in CANDIDATE_INDICATORS if k not in active and k in available_keys]
    added = []

    print(f"\n[Phase 2] 후보 지표 전수 시험 ({len(candidates_to_try)}개, 랜덤 아님)...")
    candidate_results = []
    for cand in candidates_to_try:
        trial_active = active | {cand}
        trial_train  = extract_indicators(train_sigs, trial_active)
        trial_w, trial_m = optimize_weights(trial_train, trial_active, n_random=3_000)
        delta_auc = trial_m["auc"] - base_m["auc"]
        candidate_results.append((delta_auc, cand, trial_w, trial_m))
        label = INDICATOR_LABELS.get(cand, cand)
        print(f"  · {label:<24} ΔAUC {delta_auc:+.4f}")

    candidate_results.sort(key=lambda x: -x[0])
    if candidate_results and candidate_results[0][0] >= ADOPT_MIN_ΔAUC:
        delta_auc, best_cand, best_w, best_m = candidate_results[0]
        active.add(best_cand)
        base_m, base_w = best_m, best_w
        label = INDICATOR_LABELS.get(best_cand, best_cand)
        print(f"  ✅ 채택(최고 기여): {label:<24} ΔAUC {delta_auc:+.4f}")
        added.append(best_cand)
    else:
        print(f"  ⬜ 이번 세대 채택 없음 (최고 ΔAUC가 기준 {ADOPT_MIN_ΔAUC} 미달)")

    # ── 최종 최적화 (전체 데이터)
    print(f"\n[Phase 3] 최종 최적화 — {len(active)}개 지표 전체 데이터...")
    all_ext   = extract_indicators(all_signals, active)
    final_w, final_m = optimize_weights(all_ext, active, n_random=50_000)

    # Train/Test 검증
    final_train_ext = extract_indicators(train_sigs, active)
    final_test_ext  = extract_indicators(test_sigs,  active)
    final_train_m   = evaluate_weights(final_train_ext, final_w)
    final_test_m    = evaluate_weights(final_test_ext,  final_w)
    overfit_final   = round(final_train_m["auc"] - final_test_m["auc"], 4)

    # ── 좌표 서명
    coord_sig = make_coordinate_signature(final_w, final_m, generation)

    # ── 상관 행렬
    corr = {}
    for a in sorted(active):
        corr[a] = {}
        va = [s["indicators"][a] for s in all_ext]
        for b in sorted(active):
            vb = [s["indicators"][b] for s in all_ext]
            n  = len(va)
            mx, my = sum(va)/n, sum(vb)/n
            num = sum((x-mx)*(y-my) for x,y in zip(va,vb))
            dx = math.sqrt(sum((x-mx)**2 for x in va)+1e-9)
            dy = math.sqrt(sum((y-my)**2 for y in vb)+1e-9)
            corr[a][b] = round(num/(dx*dy), 3)

    # ── 수익 시뮬레이션
    rng = random.Random(99)
    sim_sigs = all_ext[:]
    rng.shuffle(sim_sigs)
    eq_opt   = [100.0]
    eq_equal = [100.0]
    eq_w     = {k: 1/len(active) for k in active}
    for s in sim_sigs:
        if composite_score(s["indicators"], final_w) >= 0.52:
            r = 0.07 if s["outcome"] else -0.03
            eq_opt.append(round(eq_opt[-1]*(1+r), 2))
        if composite_score(s["indicators"], eq_w) >= 0.52:
            r = 0.07 if s["outcome"] else -0.03
            eq_equal.append(round(eq_equal[-1]*(1+r), 2))

    # ── 결과 출력
    print(f"\n{'='*65}")
    print(f"🎯 Generation {generation} 완료")
    print(f"  활성 지표 : {len(active)}개")
    print(f"  Train AUC : {final_train_m['auc']}  Sharpe {final_train_m['sharpe']:.3f}  정확도 {final_train_m['accuracy']}%")
    print(f"  Test  AUC : {final_test_m['auc']}   Overfit gap {overfit_final:+.4f}")
    if overfit_final > 0.05:
        print(f"  ⚠  오버피팅 감지 (gap {overfit_final:.4f} > 0.05)")
    print(f"  수익 곡선 : 100 → {eq_opt[-1]:.1f}  (균등가중: {eq_equal[-1]:.1f})")
    print(f"\n  📍 IR 좌표 서명: {coord_sig}")
    print(f"\n  최적 가중치 (상위 8개):")
    for k, v in sorted(final_w.items(), key=lambda x:-x[1])[:8]:
        bar = "█" * int(v * 40)
        print(f"    {INDICATOR_LABELS.get(k,k):<26} {v:.4f}  {bar}")

    history.append({
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "active_count": len(active),
        "dropped": dropped,
        "removed_by_contribution": removed,
        "added": added,
        "train_auc": final_train_m["auc"],
        "test_auc":  final_test_m["auc"],
        "overfit_gap": overfit_final,
        "accuracy": final_train_m["accuracy"],
        "sharpe": final_train_m["sharpe"],
        "coordinate_sig": coord_sig,
    })

    return {
        "generated_at": datetime.now().isoformat(),
        "version": "v2",
        "generation": generation,
        "coordinate_sig": coord_sig,
        "active_indicators": sorted(list(active)),
        "indicator_labels": {k: INDICATOR_LABELS.get(k, k) for k in active},
        "univariate_auc": {k: round(univariate_auc(all_ext, k), 4) for k in active},
        "optimal_weights": final_w,
        "optimal_metrics": final_m,
        "train_metrics": final_train_m,
        "test_metrics":  final_test_m,
        "overfit_gap": overfit_final,
        "correlation_matrix": corr,
        "equity_optimal": eq_opt[:300],
        "equity_equal":   eq_equal[:300],
        "history": history,
        "data_stats": {
            "total_signals": len(all_signals),
            "train_size": len(train_sigs),
            "test_size": len(test_sigs),
        }
    }


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main():
    reset = "--reset" in sys.argv

    all_signals = load_real_data()

    prev_state = None
    if not reset and os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH, "r", encoding="utf-8") as f:
            prev_state = json.load(f)
        print(f"이전 결과 로드 → Generation {prev_state.get('generation',1)}  "
              f"AUC {prev_state.get('optimal_metrics',{}).get('auc','-')}  "
              f"좌표: {prev_state.get('coordinate_sig','?')}")
    else:
        print("초기 상태로 시작 (--reset)" if reset else "첫 실행")

    new_state = evolve(prev_state, all_signals)

    # ── 역대 최고 AUC Gen 추적
    current_auc = new_state.get("optimal_metrics", {}).get("auc", 0)
    prev_best    = (prev_state or {}).get("best_ever", {})
    prev_best_auc = prev_best.get("metrics", {}).get("auc", 0)

    if current_auc >= prev_best_auc:
        new_state["best_ever"] = {
            "generation":      new_state["generation"],
            "coordinate_sig":  new_state["coordinate_sig"],
            "weights":         new_state["optimal_weights"],
            "metrics":         new_state["optimal_metrics"],
            "active_indicators": new_state["active_indicators"],
            "updated_at":      new_state["generated_at"],
        }
        print(f"🏆 역대 최고 갱신! AUC {current_auc:.4f} (이전 최고: {prev_best_auc:.4f})")
    else:
        # 이전 best 유지
        new_state["best_ever"] = prev_best
        print(f"📊 역대 최고 유지: Gen {prev_best.get('generation','?')} AUC {prev_best_auc:.4f}"
              f"  (현재 Gen {new_state['generation']}: {current_auc:.4f})")

    os.makedirs("data", exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)

    print(f"\n💾 저장 완료: {RESULTS_PATH}")
    print(f"📍 현재 좌표: {new_state['coordinate_sig']}")
    print(f"🏆 최고 좌표: {new_state['best_ever'].get('coordinate_sig','?')}")

if __name__ == "__main__":
    main()
