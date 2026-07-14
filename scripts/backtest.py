#!/usr/bin/env python3
"""
Influence Radar 3.0 - Backtest Engine v2
training_data.json 실전 데이터 기반 백테스트

평가 항목:
1. 전체 적중률 (outcome 0/1)
2. 평균 수익률 (actual_return %)
3. 인물별 성능 분석
4. 섹터별 성능 분석
5. 리포트 저장
"""

import json
import numpy as np
from datetime import datetime
import os


class BacktestEngine:
    def __init__(self, data_file="data/training_data.json"):
        self.data_file = data_file
        self.signals = None
        self.results = {
            'total_signals': 0,
            'correct_predictions': 0,
            'accuracy': 0.0,
            'avg_return': 0.0,
            'by_person': {},
            'by_sector': {},
        }

    def load_data(self):
        """학습 데이터 로드"""
        print("📥 Loading backtest data...")
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.signals = data['signals']
        print(f"✅ Loaded {len(self.signals)} signals")
        return self.signals

    def evaluate_outcomes(self):
        """적중률 및 수익률 평가"""
        print("\n📊 Evaluating Outcomes...")

        outcomes = [int(s.get('outcome', 0)) for s in self.signals]
        returns = [float(s.get('actual_return', 0)) for s in self.signals]

        hit_count = sum(outcomes)
        accuracy = hit_count / len(outcomes) * 100
        avg_return = np.mean(returns)
        max_return = np.max(returns)
        min_return = np.min(returns)
        positive_returns = sum(1 for r in returns if r > 0)

        self.results['total_signals'] = len(self.signals)
        self.results['correct_predictions'] = hit_count
        self.results['accuracy'] = round(accuracy, 2)
        self.results['avg_return'] = round(avg_return, 2)
        self.results['max_return'] = round(max_return, 2)
        self.results['min_return'] = round(min_return, 2)
        self.results['positive_return_rate'] = round(positive_returns / len(returns) * 100, 2)

        print(f"   ✅ Correct (outcome=1): {hit_count}/{len(outcomes)} ({accuracy:.1f}%)")
        print(f"   💰 Avg Return: {avg_return:.2f}%")
        print(f"   📈 Max Return: {max_return:.2f}%")
        print(f"   📉 Min Return: {min_return:.2f}%")
        print(f"   🟢 Positive Return Rate: {positive_returns}/{len(returns)}")

    def evaluate_by_person(self):
        """인물별 성능 분석"""
        print("\n👤 Analyzing Performance by Person...")

        person_stats = {}
        for sig in self.signals:
            person = sig.get('person', 'unknown')
            outcome = int(sig.get('outcome', 0))
            ret = float(sig.get('actual_return', 0))

            if person not in person_stats:
                person_stats[person] = {'total': 0, 'hits': 0, 'returns': []}

            person_stats[person]['total'] += 1
            person_stats[person]['hits'] += outcome
            person_stats[person]['returns'].append(ret)

        for person, stats in person_stats.items():
            stats['accuracy_pct'] = round(stats['hits'] / stats['total'] * 100, 1)
            stats['avg_return'] = round(np.mean(stats['returns']), 2)
            del stats['returns']

        self.results['by_person'] = person_stats

        for person, stats in sorted(person_stats.items(), key=lambda x: -x[1]['accuracy_pct']):
            print(f"   {person}: {stats['hits']}/{stats['total']} ({stats['accuracy_pct']}%), avg return {stats['avg_return']}%")

    def evaluate_by_sector(self):
        """섹터별 성능 분석"""
        print("\n🏭 Analyzing Performance by Sector...")

        sector_stats = {}
        for sig in self.signals:
            sector = sig.get('sector', 'unknown')
            outcome = int(sig.get('outcome', 0))
            ret = float(sig.get('actual_return', 0))

            if sector not in sector_stats:
                sector_stats[sector] = {'total': 0, 'hits': 0, 'returns': []}

            sector_stats[sector]['total'] += 1
            sector_stats[sector]['hits'] += outcome
            sector_stats[sector]['returns'].append(ret)

        for sector, stats in sector_stats.items():
            stats['accuracy_pct'] = round(stats['hits'] / stats['total'] * 100, 1)
            stats['avg_return'] = round(np.mean(stats['returns']), 2)
            del stats['returns']

        self.results['by_sector'] = sector_stats

        for sector, stats in sorted(sector_stats.items(), key=lambda x: -x[1]['accuracy_pct']):
            print(f"   {sector}: {stats['hits']}/{stats['total']} ({stats['accuracy_pct']}%), avg return {stats['avg_return']}%")

    def generate_report(self):
        """백테스트 리포트 생성 및 저장"""
        print("\n" + "="*60)
        print("📋 BACKTEST REPORT")
        print("="*60)

        dates = [s.get('date', '') for s in self.signals if s.get('date')]
        period = f"{min(dates)} to {max(dates)}" if dates else 'unknown'

        report = {
            'timestamp': datetime.now().isoformat(),
            'period': period,
            'results': self.results
        }

        with open('backtest_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Report saved → backtest_report.json")
        print(f"   Period         : {period}")
        print(f"   Total Signals  : {self.results['total_signals']}")
        print(f"   Accuracy       : {self.results['accuracy']}%")
        print(f"   Avg Return     : {self.results['avg_return']}%")
        print(f"   Positive Rate  : {self.results['positive_return_rate']}%")

        return report

    def run(self):
        print("\n" + "="*60)
        print("🚀 BACKTEST ENGINE v2")
        print("="*60)

        self.load_data()
        self.evaluate_outcomes()
        self.evaluate_by_person()
        self.evaluate_by_sector()
        report = self.generate_report()

        print("\n✨ Backtest Complete!")
        print("="*60)
        return report


if __name__ == "__main__":
    backtester = BacktestEngine()
    backtester.run()
