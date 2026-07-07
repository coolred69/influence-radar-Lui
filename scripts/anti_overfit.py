#!/usr/bin/env python3
"""
Influence Radar — 과적합 방지 검증 (Anti-Overfitting Module)
════════════════════════════════════════════════════════════
AI 트레이딩 실패 원인 #2 극복: 과적합 (Overfitting)
→ 해결책: Walk-Forward Validation + Monte Carlo 순열 검정

검증 로직:
  1. Walk-Forward (4-fold): 시간 순서 유지 → 각 fold 훈련→검증 AUC 비교
  2. Monte Carlo (n=200): 레이블 무작위 셔플 → 실제 AUC 통계 유의성 확인
  3. Degradation 감지: 훈련 AUC 대비 검증 AUC 15%+ 하락 = 과적합 경보

판정 기준:
  HEALTHY — fold 과적합 없음 + Monte Carlo p<0.05
  CAUTION — 경미한 경보 1개
  OVERFIT — 복수 경보 (진화 일시 중단 권고)

사용:
  python scripts/anti_overfit.py
  → data/overfit_report.json 저장
"""

import json, os, random
from datetime import datetime
import numpy as np

TRAINING_PATH = "data/training_data.json"
RESULTS_PATH  = "data/indicator_results.json"
OUTPUT_PATH   = "data/overfit_report.json"

FOLDS         = 4      # Walk-Forward fold 수
MONTE_CARLO_N = 200    # 순열 검정 반복 수
OVERFIT_WARN  = 0.15   # 훈련→검증 AUC 하락 경보 임계값 (15%)
MIN_EVENTS    = 25     # 최소 이벤트 수


def load_events():
    """훈련 데이터 로드 (시간 순 정렬, 결과 + 지표 있는 것만)"""
    if not os.path.exists(TRAINING_PATH):
        return []
    with open(TRAINING_PATH) as f:
        data = json.load(f)
    events = data.get("signals", [])
    events.sort(key=lambda x: x.get("date", ""))
    return [e for e in events if "outcome" in e and "indicators" in e]


def load_weights():
    """현재 최적 가중치 로드 (best_ever 우선)"""
    if not os.path.exists(RESULTS_PATH):
        return {}
    with open(RESULTS_PATH) as f:
        d = json.load(f)
    best = d.get("best_ever", {})
    if best and best.get("metrics", {}).get("auc", 0) >= d.get("optimal_metrics", {}).get("auc", 0):
        return best.get("weights", {})
    return d.get("optimal_weights", {})


def calc_auc(events, weights):
    """AUC 계산 (Mann-Whitney U 방식)"""
    if not events or not weights:
        return 0.5

    scored = []
    for e in events:
        inds  = e.get("indicators", {})
        score = sum(weights.get(k, 0) * inds.get(k, 0.5) for k in weights)
        scored.append((score, bool(e.get("outcome", False))))

    scored.sort(key=lambda x: -x[0])
    n_pos = sum(1 for _, o in scored if o)
    n_neg = len(scored) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    rank_sum = sum(i + 1 for i, (_, o) in enumerate(scored) if o)
    u_stat   = rank_sum - n_pos * (n_pos + 1) / 2
    return round(u_stat / (n_pos * n_neg), 4)


def walk_forward_validation(events, weights, folds=4):
    """Walk-Forward Validation: 시간 순 누적 훈련 → 다음 fold 테스트"""
    n = len(events)
    if n < folds * 5:
        return None, []

    fold_size  = n // folds
    fold_aucs  = []

    for fold in range(1, folds):
        train_end = fold * fold_size
        test_end  = min((fold + 1) * fold_size, n)

        train = events[:train_end]
        test  = events[train_end:test_end]
        if len(test) < 5:
            continue

        train_auc = calc_auc(train, weights)
        test_auc  = calc_auc(test,  weights)

        fold_aucs.append({
            "fold":        fold,
            "train_size":  len(train),
            "test_size":   len(test),
            "train_auc":   train_auc,
            "test_auc":    test_auc,
            "degradation": round(train_auc - test_auc, 4),
            "overfit_flag": (train_auc - test_auc) > OVERFIT_WARN,
        })

    if not fold_aucs:
        return None, []

    avg_test  = round(float(np.mean([f["test_auc"]    for f in fold_aucs])), 4)
    avg_deg   = round(float(np.mean([f["degradation"] for f in fold_aucs])), 4)
    return avg_test, fold_aucs


def monte_carlo_test(events, weights, n=200):
    """Monte Carlo 순열 검정: 레이블 셔플 → 통계적 유의성 확인"""
    real_auc  = calc_auc(events, weights)
    outcomes  = [bool(e.get("outcome", False)) for e in events]
    perm_aucs = []

    for _ in range(n):
        shuffled = outcomes[:]
        random.shuffle(shuffled)
        fake = [{**e, "outcome": shuffled[i]} for i, e in enumerate(events)]
        perm_aucs.append(calc_auc(fake, weights))

    perm_mean = float(np.mean(perm_aucs))
    perm_std  = float(np.std(perm_aucs))
    p_value   = sum(1 for a in perm_aucs if a >= real_auc) / n
    z_score   = (real_auc - perm_mean) / (perm_std + 1e-9)

    return {
        "real_auc":    round(real_auc,   4),
        "perm_mean":   round(perm_mean,  4),
        "perm_std":    round(perm_std,   4),
        "p_value":     round(p_value,    4),
        "z_score":     round(z_score,    2),
        "significant": bool(p_value < 0.05),
    }


def main():
    print("=" * 65)
    print("🔬 과적합 방지 검증 — Anti-Overfitting Module")
    print("=" * 65)

    events  = load_events()
    weights = load_weights()

    print(f"\n훈련 이벤트: {len(events)}개  |  가중치 지표: {len(weights)}개")

    report = {
        "validated_at": datetime.now().isoformat(),
        "event_count":  len(events),
        "weight_count": len(weights),
        "status":       "UNKNOWN",
        "warnings":     [],
        "walk_forward": None,
        "monte_carlo":  None,
        "verdict":      "",
        "recommendation": "",
    }

    if len(events) < MIN_EVENTS:
        msg = f"이벤트 부족 ({len(events)}/{MIN_EVENTS}) — 검증 스킵"
        print(f"\n⚠ {msg}")
        report["status"]  = "SKIPPED"
        report["verdict"] = msg
        report["recommendation"] = "훈련 데이터를 더 쌓은 후 재실행 (목표: 100개 이상)"
    else:
        # ── Walk-Forward Validation
        print(f"\n▸ Walk-Forward Validation ({FOLDS} folds)...")
        avg_wf, folds_result = walk_forward_validation(events, weights, FOLDS)
        report["walk_forward"] = {
            "avg_test_auc":  avg_wf,
            "avg_degradation": round(float(np.mean([f["degradation"] for f in folds_result])), 4) if folds_result else None,
            "folds":         folds_result,
        }
        for fr in folds_result:
            flag = "🔴 과적합" if fr["overfit_flag"] else "✅"
            print(f"  Fold {fr['fold']}: 훈련 {fr['train_auc']:.4f} → 검증 {fr['test_auc']:.4f}"
                  f"  (하락 {fr['degradation']:.4f})  {flag}")
        if avg_wf:
            print(f"\n  📊 평균 검증 AUC: {avg_wf:.4f}")

        # ── Monte Carlo
        print(f"\n▸ Monte Carlo 순열 검정 (n={MONTE_CARLO_N})...")
        mc = monte_carlo_test(events, weights, MONTE_CARLO_N)
        report["monte_carlo"] = mc
        sig_tag = "✅ 유의미" if mc["significant"] else "🔴 유의성 없음"
        print(f"  실제 AUC {mc['real_auc']:.4f}  |  순열 평균 {mc['perm_mean']:.4f}"
              f"  |  p={mc['p_value']:.4f}  z={mc['z_score']:.2f}  {sig_tag}")

        # ── 경보 수집
        warnings = []
        if folds_result:
            bad = sum(1 for f in folds_result if f["overfit_flag"])
            if bad:
                warnings.append(
                    f"과적합 의심 fold {bad}/{len(folds_result)}개 "
                    f"(훈련→검증 AUC 하락 >{OVERFIT_WARN:.0%})"
                )
        if not mc["significant"]:
            warnings.append(f"통계적 유의성 없음 (p={mc['p_value']:.3f}) "
                            f"— 지표가 노이즈일 수 있음")
        if avg_wf and avg_wf < 0.54:
            warnings.append(f"검증 AUC 낮음 ({avg_wf:.4f}) — 일반화 성능 부족")

        report["warnings"] = warnings

        if not warnings:
            report["status"]  = "HEALTHY"
            report["verdict"] = (f"과적합 없음  |  WF-AUC {avg_wf:.4f}  |"
                                 f"  p={mc['p_value']:.4f}")
            report["recommendation"] = "현재 가중치 신뢰 가능. 진화 계속 진행."
        elif len(warnings) == 1:
            report["status"]  = "CAUTION"
            report["verdict"] = f"주의: {warnings[0]}"
            report["recommendation"] = (
                "훈련 데이터 다양성 확보 또는 지표 수 축소 검토."
            )
        else:
            report["status"]  = "OVERFIT"
            report["verdict"] = f"과적합 경보: {'; '.join(warnings)}"
            report["recommendation"] = (
                "① 지표 수 축소 (현재 상위 6개만 유지)  "
                "② 정규화 강화  "
                "③ 훈련 데이터 증가 후 재진화 권고"
            )

        icon = {"HEALTHY": "✅", "CAUTION": "⚠", "OVERFIT": "🔴"}.get(report["status"], "?")
        print(f"\n{'='*65}")
        print(f"{icon} 최종 판정: {report['status']}")
        print(f"   {report['verdict']}")
        print(f"   💡 {report['recommendation']}")

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n💾 저장: {OUTPUT_PATH}")
    print("=" * 65)
    return report


if __name__ == "__main__":
    main()
