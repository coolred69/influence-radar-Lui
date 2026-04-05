#!/usr/bin/env python3
"""
Influence Radar 3.0 - Real-time Signal Prediction
학습된 모델을 사용하여 새로운 신호에 대해 매수가/매도가 예측

기능:
1. 학습된 모델 로드
2. 새 신호 입력
3. 예상 매수가/매도가 예측
4. 신뢰도 계산
5. 예상 매수/매도 날짜 계산 (과거 패턴 기반)
"""

import json
import pickle
import numpy as np
import os
from datetime import datetime, timedelta

class SignalPredictor:
    def __init__(self, model_dir="models"):
        self.model_dir = model_dir
        self.buy_model = None
        self.sell_model = None
        self.metadata = None
        self.load_models()
    
    def load_models(self):
        """학습된 모델 로드"""
        print("📂 Loading trained models...")
        
        try:
            with open(os.path.join(self.model_dir, 'buy_price_model.pkl'), 'rb') as f:
                self.buy_model = pickle.load(f)
            
            with open(os.path.join(self.model_dir, 'sell_price_model.pkl'), 'rb') as f:
                self.sell_model = pickle.load(f)
            
            with open(os.path.join(self.model_dir, 'metadata.json'), 'r') as f:
                self.metadata = json.load(f)
            
            print("✅ Models loaded successfully")
        except FileNotFoundError as e:
            print(f"❌ Model files not found: {e}")
            print("   Run train_model.py first")
    
    def calculate_holding_period(self, influence_score, sentiment):
        """
        과거 데이터 기반으로 보유 기간 계산
        영향력이 높고 감정이 긍정적일수록 더 길게 보유
        """
        # 기본 보유 기간 (일)
        base_buy_days = 0  # 신호 당일 매수
        base_hold_days = 7  # 기본 7일 보유
        
        # 영향력에 따른 조정 (+3일 ~ +0일)
        influence_adjustment = int(influence_score * 3)
        
        # 감정에 따른 조정
        sentiment_adjustment = {
            'positive': 3,
            'neutral': 1,
            'negative': -2
        }.get(sentiment, 0)
        
        # 최종 보유 기간
        hold_days = max(3, base_hold_days + influence_adjustment + sentiment_adjustment)
        
        return base_buy_days, hold_days
    
    def predict_signal(self, signal_input, current_price=None):
        """
        신호 예측
        
        Args:
            signal_input: {
                'person': str,
                'influence_score': float (0~1),
                'sector': str,
                'ticker': str,
                'news_headline': str,
                'signal_strength': float (0~1),
                'sentiment': str (positive/neutral/negative),
                'news_frequency': int,
                'cross_validation': list
            }
            current_price: float (현재가, 선택사항)
        
        Returns:
            예측 결과 dict
        """
        if not self.buy_model or not self.sell_model:
            print("❌ Models not loaded")
            return None
        
        # 섹터/감정 매핑
        sector_map = {
            "AI/GPU": 1,
            "Cloud/AI": 2,
            "Macro/Rates": 3,
            "Auto/Energy": 4,
            "Tech/Finance": 5
        }
        
        # 특성 벡터 구성
        feature = np.array([[
            signal_input['influence_score'],
            signal_input['signal_strength'],
            sector_map.get(signal_input['sector'], 0),
            {'positive': 1, 'neutral': 0, 'negative': -1}.get(signal_input['sentiment'], 0),
            signal_input.get('news_frequency', 1),
            len(signal_input.get('cross_validation', []))
        ]])
        
        # 정규화
        X_mean = np.array(self.metadata['scaler_info']['X_mean'])
        X_std = np.array(self.metadata['scaler_info']['X_std'])
        feature_normalized = (feature - X_mean) / (X_std + 1e-8)
        
        # 예측
        predicted_buy = self.buy_model.predict(feature_normalized)[0]
        predicted_sell = self.sell_model.predict(feature_normalized)[0]
        
        # 신뢰도 (영향력 × 신호강도 × 검증 출처 수)
        confidence = (
            signal_input['influence_score'] * 
            signal_input['signal_strength'] * 
            (1 + len(signal_input.get('cross_validation', [])) * 0.1)
        )
        confidence = min(95, max(60, int(confidence * 100)))
        
        # 매수/매도 날짜 계산
        buy_days, hold_days = self.calculate_holding_period(
            signal_input['influence_score'],
            signal_input['sentiment']
        )
        
        today = datetime.now()
        predicted_buy_date = (today + timedelta(days=buy_days)).strftime("%Y-%m-%d")
        predicted_sell_date = (today + timedelta(days=buy_days + hold_days)).strftime("%Y-%m-%d")
        
        # 예상 수익률
        expected_return = ((predicted_sell - predicted_buy) / predicted_buy) * 100
        
        result = {
            'timestamp': today.isoformat(),
            'person': signal_input['person'],
            'ticker': signal_input['ticker'],
            'sector': signal_input['sector'],
            'sentiment': signal_input['sentiment'],
            'influence_score': signal_input['influence_score'],
            'signal_strength': signal_input['signal_strength'],
            'news_headline': signal_input.get('news_headline', ''),
            'cross_validation': signal_input.get('cross_validation', []),
            'predicted_buy_price': round(predicted_buy, 2),
            'predicted_sell_price': round(predicted_sell, 2),
            'predicted_buy_date': predicted_buy_date,
            'predicted_sell_date': predicted_sell_date,
            'confidence': confidence,
            'expected_return_pct': round(expected_return, 2),
            'holding_period_days': hold_days,
            'status': 'pending'  # pending/executed/completed
        }
        
        return result
    
    def predict_batch(self, signals_list):
        """여러 신호 동시 예측"""
        results = []
        for signal in signals_list:
            prediction = self.predict_signal(signal)
            results.append(prediction)
        return results


# 예제
if __name__ == "__main__":
    predictor = SignalPredictor()
    
    # 테스트 신호
    test_signal = {
        'person': 'Jensen Huang',
        'influence_score': 0.95,
        'sector': 'AI/GPU',
        'ticker': 'NVDA',
        'news_headline': 'NVIDIA Announces New H200 AI Accelerator',
        'signal_strength': 0.88,
        'sentiment': 'positive',
        'news_frequency': 5,
        'cross_validation': ['Reuters', 'Bloomberg', 'CNBC']
    }
    
    print("\n" + "="*60)
    print("🔮 Signal Prediction")
    print("="*60)
    
    prediction = predictor.predict_signal(test_signal)
    
    if prediction:
        print(f"\n📊 Prediction Result:")
        print(f"   Person: {prediction['person']}")
        print(f"   Ticker: {prediction['ticker']}")
        print(f"   Sentiment: {prediction['sentiment'].upper()}")
        print(f"   Confidence: {prediction['confidence']}%")
        print(f"\n💰 Price Prediction:")
        print(f"   Buy Price: ${prediction['predicted_buy_price']}")
        print(f"   Sell Price: ${prediction['predicted_sell_price']}")
        print(f"   Expected Return: {prediction['expected_return_pct']}%")
        print(f"\n📅 Date Prediction:")
        print(f"   Buy Date: {prediction['predicted_buy_date']}")
        print(f"   Sell Date: {prediction['predicted_sell_date']}")
        print(f"   Holding Period: {prediction['holding_period_days']} days")
        print("\n" + "="*60)
