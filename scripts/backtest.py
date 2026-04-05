#!/usr/bin/env python3
"""
Influence Radar 3.0 - Backtest Engine
과거 3년 데이터로 모델 검증 및 적중률 분석

기능:
1. 과거 신호 로드
2. 예상값 vs 실제값 비교
3. 적중률 계산
4. 인물별/섹터별 성능 분석
5. 개선 권장사항 도출
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
            'by_person': {},
            'by_sector': {},
            'price_metrics': {},
            'date_metrics': {}
        }
    
    def load_data(self):
        """학습 데이터 로드"""
        print("📥 Loading backtest data...")
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.signals = data['signals']
        print(f"✅ Loaded {len(self.signals)} signals")
        return self.signals
    
    def evaluate_price_accuracy(self):
        """예상가 vs 실제가 정확도 평가"""
        print("\n📊 Evaluating Price Accuracy...")
        
        buy_errors = []
        sell_errors = []
        correct_count = 0
        
        for signal in self.signals:
            # 예상가 오차율
            buy_error = abs(signal['predicted_buy_price'] - signal['actual_buy_price']) / signal['actual_buy_price'] * 100
            sell_error = abs(signal['predicted_sell_price'] - signal['actual_sell_price']) / signal['actual_sell_price'] * 100
            
            buy_errors.append(buy_error)
            sell_errors.append(sell_error)
            
            # 정확도 판정 (오차 5% 이내)
            if buy_error < 5 and sell_error < 5:
                correct_count += 1
                signal['accuracy'] = 1.0
            else:
                signal['accuracy'] = max(0, 1 - (buy_error + sell_error) / 20)
        
        accuracy = (correct_count / len(self.signals)) * 100
        avg_buy_error = np.mean(buy_errors)
        avg_sell_error = np.mean(sell_errors)
        
        self.results['price_metrics'] = {
            'correct_predictions': correct_count,
            'accuracy_pct': round(accuracy, 2),
            'avg_buy_error_pct': round(avg_buy_error, 2),
            'avg_sell_error_pct': round(avg_sell_error, 2),
            'buy_mape': round(np.mean(buy_errors), 2),
            'sell_mape': round(np.mean(sell_errors), 2)
        }
        
        print(f"   ✅ Correct Predictions: {correct_count}/{len(self.signals)}")
        print(f"   📈 Accuracy: {accuracy:.2f}%")
        print(f"   💰 Avg Buy Price Error: {avg_buy_error:.2f}%")
        print(f"   💰 Avg Sell Price Error: {avg_sell_error:.2f}%")
    
    def evaluate_by_person(self):
        """인물별 성능 분석"""
        print("\n👤 Analyzing Performance by Person...")
        
        person_stats = {}
        
        for signal in self.signals:
            person = signal['person']
            
            if person not in person_stats:
                person_stats[person] = {
                    'total': 0,
                    'correct': 0,
                    'avg_accuracy': 0,
                    'signals': []
                }
            
            person_stats[person]['total'] += 1
            person_stats[person]['signals'].append({
                'date': signal['date'],
                'ticker': signal['ticker'],
                'accuracy': signal['accuracy']
            })
            
            if signal['accuracy'] >= 0.8:  # 80% 이상 정확
                person_stats[person]['correct'] += 1
        
        # 평균 정확도 계산
        for person, stats in person_stats.items():
            stats['avg_accuracy'] = np.mean([s['accuracy'] for s in stats['signals']])
            stats['accuracy_pct'] = (stats['correct'] / stats['total']) * 100
        
        self.results['by_person'] = person_stats
        
        for person, stats in sorted(person_stats.items(), key=lambda x: x[1]['avg_accuracy'], reverse=True):
            print(f"   {person}:")
            print(f"     - Total Signals: {stats['total']}")
            print(f"     - Correct: {stats['correct']}")
            print(f"     - Accuracy: {stats['accuracy_pct']:.1f}%")
            print(f"     - Avg Score: {stats['avg_accuracy']:.2f}/1.0")
    
    def evaluate_by_sector(self):
        """섹터별 성능 분석"""
        print("\n🏭 Analyzing Performance by Sector...")
        
        sector_stats = {}
        
        for signal in self.signals:
            sector = signal['sector']
            
            if sector not in sector_stats:
                sector_stats[sector] = {
                    'total': 0,
                    'correct': 0,
                    'avg_accuracy': 0,
                    'signals': []
                }
            
            sector_stats[sector]['total'] += 1
            sector_stats[sector]['signals'].append(signal['accuracy'])
            
            if signal['accuracy'] >= 0.8:
                sector_stats[sector]['correct'] += 1
        
        # 평균 정확도
        for sector, stats in sector_stats.items():
            stats['avg_accuracy'] = np.mean(stats['signals'])
            stats['accuracy_pct'] = (stats['correct'] / stats['total']) * 100
        
        self.results['by_sector'] = sector_stats
        
        for sector, stats in sorted(sector_stats.items(), key=lambda x: x[1]['avg_accuracy'], reverse=True):
            print(f"   {sector}:")
            print(f"     - Total Signals: {stats['total']}")
            print(f"     - Correct: {stats['correct']}")
            print(f"     - Accuracy: {stats['accuracy_pct']:.1f}%")
    
    def calculate_overall_metrics(self):
        """전체 메트릭 계산"""
        print("\n📈 Calculating Overall Metrics...")
        
        total_signals = len(self.signals)
        correct = sum(1 for s in self.signals if s['accuracy'] >= 0.8)
        avg_accuracy = np.mean([s['accuracy'] for s in self.signals])
        
        # 수익률 분석
        returns = []
        for signal in self.signals:
            ret = ((signal['actual_sell_price'] - signal['actual_buy_price']) / signal['actual_buy_price']) * 100
            returns.append(ret)
        
        self.results['total_signals'] = total_signals
        self.results['correct_predictions'] = correct
        self.results['accuracy'] = round(avg_accuracy * 100, 2)
        self.results['avg_return'] = round(np.mean(returns), 2)
        self.results['max_return'] = round(np.max(returns), 2)
        self.results['min_return'] = round(np.min(returns), 2)
        
        print(f"   📊 Total Signals: {total_signals}")
        print(f"   ✅ Correct: {correct} ({(correct/total_signals)*100:.1f}%)")
        print(f"   🎯 Model Accuracy: {avg_accuracy*100:.2f}%")
        print(f"   💰 Avg Return: {np.mean(returns):.2f}%")
        print(f"   📈 Max Return: {np.max(returns):.2f}%")
        print(f"   📉 Min Return: {np.min(returns):.2f}%")
    
    def generate_report(self):
        """백테스트 리포트 생성"""
        print("\n" + "="*60)
        print("📋 BACKTEST REPORT")
        print("="*60)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'period': f"{self.signals[0]['date']} to {self.signals[-1]['date']}",
            'results': self.results
        }
        
        # 파일로 저장
        with open('backtest_report.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Report saved to backtest_report.json")
        
        # 콘솔에 출력
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Period: {report['period']}")
        print(f"Total Signals Analyzed: {self.results['total_signals']}")
        print(f"Overall Accuracy: {self.results['accuracy']:.2f}%")
        print(f"Average Return: {self.results['avg_return']:.2f}%")
        
        return report
    
    def run(self):
        """전체 백테스트 실행"""
        print("\n" + "="*60)
        print("🚀 BACKTEST ENGINE - 3 Year Validation")
        print("="*60)
        
        # 1. 데이터 로드
        self.load_data()
        
        # 2. 평가
        self.evaluate_price_accuracy()
        self.evaluate_by_person()
        self.evaluate_by_sector()
        self.calculate_overall_metrics()
        
        # 3. 리포트 생성
        report = self.generate_report()
        
        print("\n✨ Backtest Complete!")
        print("="*60)
        
        return report


if __name__ == "__main__":
    backtester = BacktestEngine()
    backtester.run()
