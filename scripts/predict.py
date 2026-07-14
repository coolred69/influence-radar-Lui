#!/usr/bin/env python3
"""
Influence Radar 3.0 - Signal Predictor v2
학습된 모델(outcome_model.pkl, return_model.pkl)로 새 신호 예측

출력:
- outcome_prob  : 적중 확률 (0~1)
- predicted_return : 예상 수익률 (%)
- signal_grade  : BUY/WATCH/WAIT
"""

import json
import pickle
import numpy as np
import os
from datetime import datetime, timedelta

SECTOR_MAP = {
    "KR_SEMICON": 1, "KR_BIO": 2, "KR_IT": 3, "KR_ENERGY": 4, "KR_FINANCE": 5,
    "AI/GPU": 6, "Cloud/AI": 7, "Macro/Rates": 8, "Auto/Energy": 9, "Tech/Finance": 10
}


class SignalPredictor:
    def __init__(self, model_dir="models"):
        self.model_dir = model_dir
        self.outcome_model = None
        self.return_model = None
        self.metadata = None
        self.load_models()

    def load_models(self):
        """학습된 모델 로드"""
        print("📂 Loading trained models...")
        try:
            with open(os.path.join(self.model_dir, 'outcome_model.pkl'), 'rb') as f:
                self.outcome_model = pickle.load(f)

            with open(os.path.join(self.model_dir, 'return_model.pkl'), 'rb') as f:
                self.return_model = pickle.load(f)

            with open(os.path.join(self.model_dir, 'metadata.json'), 'r') as f:
                self.metadata = json.load(f)

            trained_at = self.metadata.get('trained_at', 'unknown')
            total = self.metadata.get('total_signals', 'unknown')
            print(f"✅ Models loaded (trained_at: {trained_at}, signals: {total})")
        except FileNotFoundError as e:
            print(f"❌ Model files not found: {e}")
            print("   Run train_model.py first")

    def _build_feature(self, indicators, sector):
        """indicators dict → feature vector"""
        ind = indicators
        feature = [
            float(ind.get('rsi_filter', 0)),
            float(ind.get('rsi_raw', 50)) / 100.0,
            float(ind.get('macd_align', 0)),
            float(ind.get('volume_surge', 0)),
            float(ind.get('volume_ratio', 0)),
            float(ind.get('bollinger_pos', 0.5)),
            float(ind.get('momentum_5d', 0)),
            float(ind.get('gap_up', 0)),
            float(ind.get('price_vs_52w', 0.5)),
            float(ind.get('atr_stability', 0.5)),
            float(ind.get('trend_dir_20', 0)),
            float(ind.get('pre_run_inv', 0)),
            float(ind.get('hit_rate', 0)),
            float(ind.get('sentiment', 0)),
            float(ind.get('cross_val', 0)),
            float(ind.get('news_freq', 0)),
            float(ind.get('signal_strength', 0)),
            float(SECTOR_MAP.get(sector, 0)) / 10.0,
        ]
        return np.array(feature)

    def predict(self, indicators, sector, person='unknown', symbol='', statement=''):
        """
        신호 예측

        Args:
            indicators (dict): signal_engine이 생성하는 indicators 딕셔너리
            sector (str): 섹터명
            person (str): 인플루언서명
            symbol (str): 종목 심볼
            statement (str): 발언 내용

        Returns:
            dict: 예측 결과
        """
        if not self.outcome_model or not self.return_model:
            print("❌ Models not loaded")
            return None

        # 정규화
        feature = self._build_feature(indicators, sector)
        X_mean = np.array(self.metadata['scaler_info']['X_mean'])
        X_std = np.array(self.metadata['scaler_info']['X_std'])
        feature_norm = (feature - X_mean) / (X_std + 1e-8)
        feature_2d = feature_norm.reshape(1, -1)

        # 예측
        outcome_prob = float(self.outcome_model.predict_proba(feature_2d)[0][1])
        predicted_return = float(self.return_model.predict(feature_2d)[0])

        # 등급 결정
        score = outcome_prob * 100
        if score >= 70:
            grade = 'BUY'
        elif score >= 45:
            grade = 'WATCH'
        else:
            grade = 'WAIT'

        # 예상 보유기간 (수익률 기반)
        hold_days = max(3, min(30, int(abs(predicted_return) * 2)))

        today = datetime.now()
        result = {
            'timestamp': today.isoformat(),
            'person': person,
            'symbol': symbol,
            'sector': sector,
            'statement': statement,
            'outcome_prob': round(outcome_prob, 4),
            'predicted_return_pct': round(predicted_return, 2),
            'signal_grade': grade,
            'score': round(score, 1),
            'hold_days': hold_days,
            'predicted_exit_date': (today + timedelta(days=hold_days)).strftime('%Y-%m-%d'),
        }

        return result

    def predict_from_signal(self, signal_dict):
        """signal_engine 출력 형식 직접 수용"""
        return self.predict(
            indicators=signal_dict.get('indicators', {}),
            sector=signal_dict.get('sector', ''),
            person=signal_dict.get('person', ''),
            symbol=signal_dict.get('symbol', ''),
            statement=signal_dict.get('statement', ''),
        )


if __name__ == "__main__":
    predictor = SignalPredictor()

    if not predictor.outcome_model:
        print("모델 없음 — train_model.py 먼저 실행하세요")
        exit(0)

    # 테스트 신호
    test_indicators = {
        'rsi_filter': 1, 'rsi_raw': 62.7, 'macd_align': 1,
        'volume_surge': 0, 'volume_ratio': 0.5, 'bollinger_pos': 0.676,
        'momentum_5d': 0.6, 'gap_up': 0.5, 'price_vs_52w': 0.95,
        'atr_stability': 0.8, 'trend_dir_20': 1, 'pre_run_inv': 0.3,
        'hit_rate': 0.7, 'sentiment': 1, 'cross_val': 0.8,
        'news_freq': 0.7, 'signal_strength': 0.85
    }

    result = predictor.predict(
        indicators=test_indicators,
        sector='AI/GPU',
        person='Jensen Huang',
        symbol='NVDA',
        statement='NVIDIA H200 AI Accelerator 발표'
    )

    if result:
        print("\n" + "="*60)
        print("🔮 Prediction Result")
        print("="*60)
        print(f"   Person         : {result['person']}")
        print(f"   Symbol         : {result['symbol']}")
        print(f"   Signal Grade   : {result['signal_grade']}  (score: {result['score']})")
        print(f"   Outcome Prob   : {result['outcome_prob']:.1%}")
        print(f"   Expected Return: {result['predicted_return_pct']}%")
        print(f"   Hold Days      : {result['hold_days']}일")
        print(f"   Exit Date      : {result['predicted_exit_date']}")
        print("="*60)
