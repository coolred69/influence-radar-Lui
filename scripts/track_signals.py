#!/usr/bin/env python3
"""
Influence Radar — 실전 피드백 루프 (Phase 3)
════════════════════════════════════════════════════════════
매주 실행: 과거 BUY 신호 결과 추적 → 훈련 데이터에 자동 추가

파이프라인:
  1. data/signal_history.json 로드 (signal_engine이 저장한 BUY 기록)
  2. 평가 대상 필터: 발생 후 10거래일 경과 + 아직 미평가
  3. yfinance로 당시 ~ 현재 가격 확인
  4. 수익 여부 판단 (10일 후 +3% → 성공)
  5. data/training_data.json에 새 이벤트로 추가
  6. 승률, 평균 수익률, 손익비 통계 업데이트

자동 실행: .github/workflows/track-signals.yml (주 1회 수요일)
"""

import json, os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

HISTORY_PATH  = "data/signal_history.json"
TRAINING_PATH = "data/training_data.json"
STATS_PATH    = "data/performance_stats.json"

HOLD_DAYS     = 10    # 평가 기간 (거래일 기준)
TARGET_RET    = 0.03  # 성공 기준 (3% 이상 상승)
STOP_LOSS_RET = -0.05 # 손절 기준 (-5% 이하)
MIN_DAYS_OLD  = 12    # 최소 경과 일수 (여유 포함)

# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def trading_days_elapsed(date_str):
    """date_str ~ 오늘 사이 영업일 수 (대략 계산)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    now = datetime.now()
    delta_days = (now - dt).days
    # 영업일 ≈ 전체일 * 5/7
    return int(delta_days * 5 / 7)


def fetch_outcome(symbol, signal_date, entry_price):
    """신호 발생 후 10거래일 수익 판단"""
    try:
        dt    = datetime.strptime(signal_date, "%Y-%m-%d")
        start = (dt - timedelta(days=2)).strftime("%Y-%m-%d")
        end   = (dt + timedelta(days=HOLD_DAYS * 2 + 5)).strftime("%Y-%m-%d")

        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df.empty or len(df) < 5:
            return None, None, None

        df.index = pd.to_datetime(df.index).tz_localize(None)
        dates = df.index.normalize()
        ev_dt = pd.Timestamp(signal_date)

        # 진입 위치
        pos_arr = [i for i, d in enumerate(dates) if d >= ev_dt]
        if not pos_arr:
            return None, None, None
        entry_pos = pos_arr[0]

        # 실제 진입가 (당일 종가)
        actual_entry = float(df['Close'].iloc[entry_pos])

        # 10거래일 후 종가
        exit_pos = entry_pos + HOLD_DAYS
        if exit_pos >= len(df):
            # 데이터 부족 → 마지막 가격 사용
            exit_pos = len(df) - 1

        exit_price = float(df['Close'].iloc[exit_pos])
        ret = (exit_price - actual_entry) / (actual_entry + 1e-9)

        # 최대 낙폭 (최고점 대비)
        window = df['Close'].iloc[entry_pos:exit_pos+1]
        max_dd = float((window.min() - actual_entry) / (actual_entry + 1e-9)) if len(window) > 0 else 0

        outcome = ret >= TARGET_RET
        return outcome, round(ret * 100, 2), round(max_dd * 100, 2)

    except Exception as e:
        print(f"  ⚠ {symbol} 가격 수집 실패: {e}")
        return None, None, None


# ──────────────────────────────────────────────────────────────
# 신호 히스토리 처리
# ──────────────────────────────────────────────────────────────

def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH) as f:
        return json.load(f).get("signals", [])


def save_history(signals):
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now().isoformat(), "signals": signals},
                  f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────
# 훈련 데이터 업데이트
# ──────────────────────────────────────────────────────────────

def append_to_training(new_events):
    """검증된 실전 신호를 training_data.json에 추가"""
    if not new_events:
        return 0

    if os.path.exists(TRAINING_PATH):
        with open(TRAINING_PATH) as f:
            td = json.load(f)
    else:
        td = {"version": "v2", "signals": [], "hit_rates_by_person": {}}

    existing_keys = {(s["date"], s["symbol"]) for s in td.get("signals", [])}
    added = 0

    for ev in new_events:
        key = (ev["date"], ev["symbol"])
        if key in existing_keys:
            continue

        # training_data 형식에 맞게 변환
        td_signal = {
            "date":        ev["date"],
            "person":      ev.get("influencer", "live_signal"),
            "symbol":      ev["symbol"],
            "event":       f"[LIVE] IR-COORD {ev.get('signal','BUY')} 신호 검증",
            "sentiment":   "positive" if ev.get("outcome") else "negative",
            "sector":      ev.get("sector", "Unknown"),
            "confidence":  ev.get("score", 70) / 100,
            "outcome":     ev.get("outcome", False),
            "return_pct":  ev.get("return_pct", 0),
            "source":      "live_tracking",
        }
        # indicators는 신호 발생 시 저장된 값 활용
        if "indicators" in ev:
            td_signal["indicators"] = ev["indicators"]

        td["signals"].append(td_signal)
        existing_keys.add(key)
        added += 1

    if added > 0:
        td["version"] = "v2"
        td["last_live_update"] = datetime.now().isoformat()
        with open(TRAINING_PATH, "w", encoding="utf-8") as f:
            json.dump(td, f, indent=2, ensure_ascii=False)

    return added


# ──────────────────────────────────────────────────────────────
# 성과 통계 계산
# ──────────────────────────────────────────────────────────────

def calc_performance_stats(evaluated_signals):
    """전체 실전 신호 성과 집계"""
    done = [s for s in evaluated_signals if s.get("evaluated") and s.get("return_pct") is not None]
    if not done:
        return {}

    rets = [s["return_pct"] for s in done]
    wins = [s for s in done if s.get("outcome")]
    losses = [s for s in done if not s.get("outcome")]

    avg_win  = sum(s["return_pct"] for s in wins)  / max(len(wins), 1)
    avg_loss = sum(s["return_pct"] for s in losses) / max(len(losses), 1)

    # 종목별 성과
    by_symbol = {}
    for s in done:
        sym = s["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"count": 0, "wins": 0, "total_ret": 0}
        by_symbol[sym]["count"] += 1
        by_symbol[sym]["total_ret"] = round(by_symbol[sym]["total_ret"] + s["return_pct"], 2)
        if s.get("outcome"):
            by_symbol[sym]["wins"] += 1

    return {
        "total_signals":   len(done),
        "win_count":       len(wins),
        "loss_count":      len(losses),
        "win_rate":        round(len(wins) / max(len(done), 1) * 100, 1),
        "avg_return_pct":  round(sum(rets) / max(len(rets), 1), 2),
        "avg_win_pct":     round(avg_win, 2),
        "avg_loss_pct":    round(avg_loss, 2),
        "profit_factor":   round(abs(avg_win / avg_loss) if avg_loss != 0 else 0, 2),
        "best_trade":      round(max(rets), 2) if rets else 0,
        "worst_trade":     round(min(rets), 2) if rets else 0,
        "by_symbol":       by_symbol,
        "updated_at":      datetime.now().isoformat(),
    }


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("📊 실전 피드백 루프 — Phase 3")
    print("=" * 65)

    signals = load_history()
    print(f"히스토리: 총 {len(signals)}건")

    # 평가 대상 필터링
    pending = [
        s for s in signals
        if not s.get("evaluated")
        and trading_days_elapsed(s.get("date", "2020-01-01")) >= HOLD_DAYS
    ]
    print(f"평가 대상: {len(pending)}건\n")

    if not pending:
        print("ℹ 평가 대상 없음 (신호 발생 후 10거래일 미경과)")
    else:
        newly_evaluated = []

        for s in pending:
            sym    = s.get("symbol", "")
            date   = s.get("date", "")
            entry  = s.get("entry_price", s.get("price", 0))
            print(f"  평가 중: {sym} ({date}) 진입가 {entry:,.2f}")

            outcome, ret_pct, max_dd = fetch_outcome(sym, date, entry)
            if outcome is None:
                print(f"    → 데이터 수집 실패, 건너뜀")
                continue

            s["evaluated"]  = True
            s["outcome"]    = outcome
            s["return_pct"] = ret_pct
            s["max_drawdown_pct"] = max_dd
            s["evaluated_at"] = datetime.now().isoformat()

            tag = "✅ 성공" if outcome else "❌ 실패"
            print(f"    → {tag}  수익률 {ret_pct:+.1f}%  최대낙폭 {max_dd:.1f}%")
            newly_evaluated.append(s)

        # 히스토리 업데이트
        for s in signals:
            for ev in newly_evaluated:
                if s.get("date") == ev.get("date") and s.get("symbol") == ev.get("symbol"):
                    s.update(ev)

        save_history(signals)
        print(f"\n💾 히스토리 업데이트: {len(newly_evaluated)}건 평가 완료")

        # 훈련 데이터 추가
        added = append_to_training(newly_evaluated)
        if added > 0:
            print(f"📚 훈련 데이터 {added}건 추가 (training_data.json)")
        else:
            print("ℹ 훈련 데이터 추가 없음 (이미 존재)")

    # 성과 통계 계산
    evaluated_all = [s for s in signals if s.get("evaluated")]
    if evaluated_all:
        stats = calc_performance_stats(evaluated_all)
        os.makedirs("data", exist_ok=True)
        with open(STATS_PATH, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*65}")
        print(f"📈 실전 성과 요약 ({stats['total_signals']}건 평가)")
        print(f"  승률:        {stats['win_rate']}%")
        print(f"  평균 수익률: {stats['avg_return_pct']:+.2f}%")
        print(f"  평균 승리:   {stats['avg_win_pct']:+.2f}%")
        print(f"  평균 손실:   {stats['avg_loss_pct']:+.2f}%")
        print(f"  손익비:      {stats['profit_factor']}")
        print(f"  최고 거래:   +{stats['best_trade']}%")
        print(f"  최악 거래:   {stats['worst_trade']}%")
    else:
        print("\nℹ 아직 평가 완료된 신호 없음")

    print("\n✅ 피드백 루프 완료")

if __name__ == "__main__":
    main()
