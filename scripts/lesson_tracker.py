#!/usr/bin/env python3
"""
Influence Radar — 실패 교훈 누적기 (Lesson Tracker) — Phase 4
════════════════════════════════════════════════════════════
AI 트레이딩 실패 원인 #3 극복: 실패 패턴 무시 (Ignoring Failure Patterns)
→ 해결책: 실패한 BUY 신호마다 "왜 실패했는가" 자동 분류 → 교정 목록 누적

분석 항목 (실패 원인 8가지):
  1. RSI_OVERBOUGHT    — RSI ≥ 65에서 진입 (과매수 진입)
  2. PRE_RUN           — 5일 수익률이 이미 +8%+ (이미 뛰어버린 종목)
  3. VOLATILE_REGIME   — 신호 발생 시 시장 VOLATILE/BEAR 국면
  4. LOW_VOLUME        — 거래량 서지 없음 (volume_surge = 0)
  5. MACD_FALSE_POS    — MACD 정렬이 약했음 (macd_align < 0.5)
  6. WEAK_TREND        — 추세 방향 중립 (trend_dir_20 < 0.5)
  7. LOW_SCORE_ENTRY   — 점수 65~68% 경계선에서 진입 (낮은 확신)
  8. HIGH_VOLATILITY   — ATR 안정성 낮음 (atr_stability < 0.3)

누적 학습:
  - 각 실패 원인의 빈도와 평균 손실 추적
  - 경보 임계값 초과 시 자동 교정 제안 생성
  - 교정 제안을 lessons_learned.json에 저장
  - 다음 진화 사이클에서 indicator_lab이 이 교훈을 반영

사용:
  python scripts/lesson_tracker.py
  → data/lessons_learned.json 저장
"""

import json, os
from datetime import datetime
import numpy as np

HISTORY_PATH  = "data/signal_history.json"
REGIME_PATH   = "data/market_regime.json"
OUTPUT_PATH   = "data/lessons_learned.json"

# 실패 원인 분류 임계값
THRESHOLDS = {
    "RSI_OVERBOUGHT":  {"field": "rsi_raw",       "condition": ">=", "value": 65,   "weight": 1.2},
    "PRE_RUN":         {"field": "pre_run_inv",    "condition": "<=", "value": 0.25, "weight": 1.1},
    "LOW_VOLUME":      {"field": "volume_surge",   "condition": "==", "value": 0,    "weight": 1.0},
    "MACD_FALSE_POS":  {"field": "macd_align",     "condition": "<=", "value": 0.5,  "weight": 0.9},
    "WEAK_TREND":      {"field": "trend_dir_20",   "condition": "<=", "value": 0.5,  "weight": 0.9},
    "LOW_SCORE_ENTRY": {"field": "_score",         "condition": "<=", "value": 68,   "weight": 0.8},
    "HIGH_VOLATILITY": {"field": "atr_stability",  "condition": "<=", "value": 0.30, "weight": 1.0},
}

# 교정 제안 (원인 → 구체 행동)
CORRECTIONS = {
    "RSI_OVERBOUGHT":  "RSI 상한 임계값을 65→60으로 낮출 것 (rsi_filter 기준 강화)",
    "PRE_RUN":         "5일 수익률 +5% 이상 종목은 BUY 억제 (pre_run_inv 가중치 증가)",
    "VOLATILE_REGIME": "VOLATILE/BEAR 국면 감지 시 BUY 임계값 75%+ 유지",
    "LOW_VOLUME":      "volume_surge=0 종목 BUY 금지 또는 volume_surge 가중치 +20%",
    "MACD_FALSE_POS":  "MACD 단독 조건 불충분 — macd+RSI 동시 만족 조건 추가",
    "WEAK_TREND":      "trend_dir_20 가중치 증가 — 추세 없는 종목 억제",
    "LOW_SCORE_ENTRY": "BUY 임계값을 65%→67%로 상향 (경계선 신호 제거)",
    "HIGH_VOLATILITY": "atr_stability < 0.3 종목 스킵 — 변동성 과다 억제",
}

# 경보 기준 (경고 출력 임계)
ALERT_THRESHOLD_COUNT = 3     # N건 이상 같은 원인 = 경보
ALERT_THRESHOLD_RATE  = 0.40  # 해당 원인 실패율 40%+ = 경보


def load_failed_signals():
    """평가 완료된 실패 신호 로드"""
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH) as f:
        data = json.load(f)
    signals = data.get("signals", [])
    return [s for s in signals if s.get("evaluated") and s.get("outcome") == False]


def load_all_evaluated():
    """전체 평가 완료 신호 (성공 + 실패)"""
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH) as f:
        data = json.load(f)
    return [s for s in data.get("signals", []) if s.get("evaluated")]


def check_failure_reason(signal):
    """단일 실패 신호의 원인 분류 (복수 가능)"""
    reasons = []
    inds    = signal.get("indicators", {})
    score   = signal.get("score", 0)

    for reason, cfg in THRESHOLDS.items():
        field = cfg["field"]
        cond  = cfg["condition"]
        val   = cfg["value"]

        if field == "_score":
            actual = score
        else:
            actual = inds.get(field, None)

        if actual is None:
            continue

        if   cond == ">="  and actual >= val: reasons.append(reason)
        elif cond == "<="  and actual <= val: reasons.append(reason)
        elif cond == ">"   and actual >  val: reasons.append(reason)
        elif cond == "<"   and actual <  val: reasons.append(reason)
        elif cond == "=="  and actual == val: reasons.append(reason)

    # 국면 정보 추가 (별도 체크)
    # 신호 저장 시 국면 정보가 없으면 스킵
    regime_at_signal = signal.get("regime", None)
    if regime_at_signal in ("BEAR", "VOLATILE"):
        reasons.append("VOLATILE_REGIME")

    return reasons if reasons else ["UNKNOWN"]


def analyze_lessons(failed_signals, all_evaluated):
    """실패 원인 집계 및 교훈 생성"""
    reason_stats = {}

    for s in failed_signals:
        reasons   = check_failure_reason(s)
        ret_pct   = s.get("return_pct", 0) or 0
        max_dd    = s.get("max_drawdown_pct", 0) or 0

        for reason in reasons:
            if reason not in reason_stats:
                reason_stats[reason] = {
                    "count":       0,
                    "total_loss":  0.0,
                    "avg_loss":    0.0,
                    "signals":     [],
                }
            reason_stats[reason]["count"]       += 1
            reason_stats[reason]["total_loss"]  += ret_pct
            reason_stats[reason]["signals"].append({
                "symbol":   s.get("symbol", ""),
                "date":     s.get("date", ""),
                "score":    s.get("score", 0),
                "ret_pct":  ret_pct,
                "max_dd":   max_dd,
            })

    # 평균 손실 계산
    for r in reason_stats:
        cnt = reason_stats[r]["count"]
        if cnt > 0:
            reason_stats[r]["avg_loss"] = round(reason_stats[r]["total_loss"] / cnt, 2)
            reason_stats[r]["total_loss"] = round(reason_stats[r]["total_loss"], 2)

    # 전체 실패율 계산
    n_total = len(all_evaluated)
    n_fail  = len(failed_signals)
    overall_fail_rate = round(n_fail / max(n_total, 1) * 100, 1)

    # 교정 제안 생성 (경보 임계 초과)
    alerts      = []
    corrections = []

    for reason, stats in sorted(reason_stats.items(), key=lambda x: -x[1]["count"]):
        rate = stats["count"] / max(n_fail, 1)
        stats["failure_rate_pct"] = round(rate * 100, 1)

        if stats["count"] >= ALERT_THRESHOLD_COUNT or rate >= ALERT_THRESHOLD_RATE:
            alert = {
                "reason":     reason,
                "count":      stats["count"],
                "rate_pct":   stats["failure_rate_pct"],
                "avg_loss":   stats["avg_loss"],
                "correction": CORRECTIONS.get(reason, "수동 검토 필요"),
                "priority":   "HIGH" if rate >= 0.5 else "MEDIUM",
            }
            alerts.append(alert)
            corrections.append(CORRECTIONS.get(reason, "수동 검토 필요"))

    # 중요도 순 정렬
    alerts.sort(key=lambda x: -x["count"])

    return {
        "reason_stats":      reason_stats,
        "alerts":            alerts,
        "corrections":       corrections,
        "overall_fail_rate": overall_fail_rate,
        "total_evaluated":   n_total,
        "total_failed":      n_fail,
    }


def load_existing_lessons():
    """기존 교훈 파일 로드 (누적용)"""
    if not os.path.exists(OUTPUT_PATH):
        return {"history": [], "cumulative_stats": {}}
    with open(OUTPUT_PATH) as f:
        return json.load(f)


def main():
    print("=" * 65)
    print("📚 실패 교훈 누적기 — Lesson Tracker (Phase 4)")
    print("=" * 65)

    failed     = load_failed_signals()
    all_eval   = load_all_evaluated()
    existing   = load_existing_lessons()

    print(f"\n평가 완료: {len(all_eval)}건  |  실패: {len(failed)}건")

    if not failed:
        print("\nℹ 분석할 실패 신호 없음 (아직 평가 완료된 실패 없음)")
        report = {
            "analyzed_at":   datetime.now().isoformat(),
            "total_failed":  0,
            "total_evaluated": len(all_eval),
            "alerts":        [],
            "corrections":   [],
            "reason_stats":  {},
            "history":       existing.get("history", []),
            "cumulative_stats": existing.get("cumulative_stats", {}),
        }
    else:
        analysis = analyze_lessons(failed, all_eval)

        print(f"\n전체 실패율: {analysis['overall_fail_rate']}%")
        print("\n▸ 실패 원인 분류:")
        for reason, stats in sorted(analysis["reason_stats"].items(),
                                    key=lambda x: -x[1]["count"]):
            print(f"  {reason:<22} {stats['count']:>3}건  "
                  f"실패율 {stats['failure_rate_pct']:>5.1f}%  "
                  f"평균손실 {stats['avg_loss']:>+6.2f}%")

        if analysis["alerts"]:
            print(f"\n{'='*65}")
            print(f"🚨 교정 권고 ({len(analysis['alerts'])}건):")
            for a in analysis["alerts"]:
                icon = "🔴" if a["priority"] == "HIGH" else "🟡"
                print(f"\n  {icon} [{a['priority']}] {a['reason']}")
                print(f"     발생: {a['count']}건 ({a['rate_pct']:.0f}%)  "
                      f"평균손실: {a['avg_loss']:+.2f}%")
                print(f"     교정: {a['correction']}")
        else:
            print("\n✅ 경보 임계 초과 원인 없음")

        # 누적 히스토리 업데이트
        today_entry = {
            "date":          datetime.now().strftime("%Y-%m-%d"),
            "total_failed":  analysis["total_failed"],
            "overall_fail_rate": analysis["overall_fail_rate"],
            "alerts":        analysis["alerts"],
            "top_reasons":   sorted(
                [(r, s["count"]) for r, s in analysis["reason_stats"].items()],
                key=lambda x: -x[1]
            )[:5],
        }

        history = existing.get("history", [])
        # 오늘 날짜 중복 방지
        history = [h for h in history if h.get("date") != today_entry["date"]]
        history.append(today_entry)

        # 누적 통계 업데이트
        cum_stats = existing.get("cumulative_stats", {})
        for reason, stats in analysis["reason_stats"].items():
            if reason not in cum_stats:
                cum_stats[reason] = {
                    "total_count": 0, "total_loss": 0.0,
                    "correction": CORRECTIONS.get(reason, "수동 검토 필요"),
                    "first_seen": datetime.now().strftime("%Y-%m-%d"),
                }
            cum_stats[reason]["total_count"] += stats["count"]
            cum_stats[reason]["total_loss"]  = round(
                cum_stats[reason]["total_loss"] + stats["total_loss"], 2)
            cum_stats[reason]["last_seen"]    = datetime.now().strftime("%Y-%m-%d")
            cum_stats[reason]["avg_loss"]     = round(
                cum_stats[reason]["total_loss"] / max(cum_stats[reason]["total_count"], 1), 2)

        report = {
            "analyzed_at":     datetime.now().isoformat(),
            "total_failed":    analysis["total_failed"],
            "total_evaluated": analysis["total_evaluated"],
            "overall_fail_rate": analysis["overall_fail_rate"],
            "alerts":          analysis["alerts"],
            "corrections":     analysis["corrections"],
            "reason_stats":    analysis["reason_stats"],
            "history":         history,
            "cumulative_stats": cum_stats,
        }

        # 누적 통계 출력
        print(f"\n{'='*65}")
        print("📊 누적 교훈 통계 (전체 기간):")
        for reason, cs in sorted(cum_stats.items(), key=lambda x: -x[1]["total_count"]):
            print(f"  {reason:<22} 누적 {cs['total_count']:>3}건  "
                  f"누적손실 {cs['total_loss']:>+7.2f}%")

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n💾 저장: {OUTPUT_PATH}")
    print("=" * 65)
    return report


if __name__ == "__main__":
    main()
