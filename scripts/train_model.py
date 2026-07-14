#!/usr/bin/env python3
"""
Influence Radar 3.0 - ML Model Training v2
training_data.json (실전 누적 데이터) 기반 학습

모델 2종:
1. RandomForestClassifier  → 신호 적중 여부 예측 (outcome 0/1)
2. RandomForestRegressor   → 예상 수익률 예측 (actual_return %)

Feature: indicators 18개 지표 + sector 인코딩
"""

import json
import pickle
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
import os
from datetime import datetime

SECTOR_MAP = {
    "KR_SEMICON": 1, "KR_BIO": 2, "KR_IT": 3, "KR_ENERGY": 4, "KR_FINANCE": 5,
    "AI/GPU": 6, "Cloud/AI": 7, "Macro/Rates": 8, "Auto/Energy": 9, "Tech/Finance": 10
}

class InfluenceRadarML:
    def __init__(self, data_file="data/training_data.json", model_dir="models"):
        self.data_file = data_file
        self.model_dir = model_dir
        self.outcome_model = None
        self.return_model = None
        self.feature_names = None
        self.scaler_info = {}
        os.makedirs(model_dir, exist_ok=True)

    def load_training_data(self):
        """학습 데이터 로드"""
        print("📥 Loading training data...")
        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.signals = data['signals']
        total = data.get('total_signals', len(self.signals))
        generated = data.get('generated_at', 'unknown')
        pos_rate = data.get('positive_rate', 'unknown')
        print(f"✅ Loaded {len(self.signals)} signals (total: {total})")
        print(f"   generated_at: {generated}, positive_rate: {pos_rate}")
        return self.signals

    def prepare_features(self):
        """indicators 기반 Feature 행렬 구성"""
        print("\n🔧 Preparing features...")

        X, y_outcome, y_return = [], [], []

        for sig in self.signals:
            ind = sig.get('indicators', {})
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
                float(SECTOR_MAP.get(sig.get('sector', ''), 0)) / 10.0,
            ]
            X.append(feature)
            y_outcome.append(int(sig.get('outcome', 0)))
            y_return.append(float(sig.get('actual_return', 0)))

        self.feature_names = [
            'rsi_filter', 'rsi_raw_norm', 'macd_align', 'volume_surge', 'volume_ratio',
            'bollinger_pos', 'momentum_5d', 'gap_up', 'price_vs_52w', 'atr_stability',
            'trend_dir_20', 'pre_run_inv', 'hit_rate', 'sentiment', 'cross_val',
            'news_freq', 'signal_strength', 'sector_norm'
        ]

        X = np.array(X)
        y_outcome = np.array(y_outcome)
        y_return = np.array(y_return)

        self.scaler_info = {
            'X_mean': X.mean(axis=0).tolist(),
            'X_std': X.std(axis=0).tolist()
        }
        X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)

        hit_rate = y_outcome.mean()
        avg_return = y_return.mean()
        print(f"✅ Features: {X.shape}, 적중률: {hit_rate:.1%}, 평균수익률: {avg_return:.2f}%")
        return X_norm, y_outcome, y_return

    def train_models(self, X, y_outcome, y_return):
        """모델 학습"""
        print("\n🧠 Training Random Forest models...")

        test_size = 0.2 if len(X) >= 20 else 0.1
        X_tr, X_te, yo_tr, yo_te, yr_tr, yr_te = train_test_split(
            X, y_outcome, y_return, test_size=test_size, random_state=42
        )

        # 모델 1: 적중 분류
        print("\n  📊 Training Outcome Classifier...")
        self.outcome_model = RandomForestClassifier(
            n_estimators=100, max_depth=10, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        self.outcome_model.fit(X_tr, yo_tr)
        yo_pred = self.outcome_model.predict(X_te)
        acc = accuracy_score(yo_te, yo_pred)
        print(f"  ✅ Outcome Accuracy: {acc:.1%}")

        # 모델 2: 수익률 예측
        print("\n  📊 Training Return Regressor...")
        self.return_model = RandomForestRegressor(
            n_estimators=100, max_depth=10, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        self.return_model.fit(X_tr, yr_tr)
        yr_pred = self.return_model.predict(X_te)
        mae = mean_absolute_error(yr_te, yr_pred)
        r2 = r2_score(yr_te, yr_pred) if len(yr_te) > 1 else 0.0
        print(f"  ✅ Return MAE: {mae:.2f}%, R²: {r2:.4f}")

        # Feature 중요도 Top5
        print("\n  📈 Top 5 Important Features:")
        importances = self.outcome_model.feature_importances_
        top5 = sorted(zip(self.feature_names, importances), key=lambda x: -x[1])[:5]
        for name, imp in top5:
            print(f"     {name}: {imp:.4f}")

        return {'accuracy': acc, 'return_mae': mae, 'return_r2': r2}

    def save_models(self):
        """모델 저장"""
        print("\n💾 Saving models...")

        with open(os.path.join(self.model_dir, 'outcome_model.pkl'), 'wb') as f:
            pickle.dump(self.outcome_model, f)

        with open(os.path.join(self.model_dir, 'return_model.pkl'), 'wb') as f:
            pickle.dump(self.return_model, f)

        metadata = {
            'trained_at': datetime.now().isoformat(),
            'feature_names': self.feature_names,
            'scaler_info': self.scaler_info,
            'total_signals': len(self.signals),
            'data_file': self.data_file,
            'model_version': '2.0'
        }
        with open(os.path.join(self.model_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✅ Models saved → {self.model_dir}/outcome_model.pkl, return_model.pkl")

    def run(self):
        print("\n" + "="*60)
        print("🚀 Influence Radar 3.0 - ML Training Pipeline v2")
        print("="*60)

        self.load_training_data()
        X, y_outcome, y_return = self.prepare_features()
        metrics = self.train_models(X, y_outcome, y_return)
        self.save_models()

        print("\n" + "="*60)
        print("✨ Training Complete!")
        print("="*60)
        print(f"\n📊 Model Performance:")
        print(f"   Outcome Accuracy : {metrics['accuracy']:.1%}")
        print(f"   Return MAE       : {metrics['return_mae']:.2f}%")
        print(f"   Return R²        : {metrics['return_r2']:.4f}")


if __name__ == "__main__":
    trainer = InfluenceRadarML()
    trainer.run()
