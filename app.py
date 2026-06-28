#!/usr/bin/env python3
"""
Influence Radar ML API Server
Deploy: Render.com (free tier)
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import json, os, pickle
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 인메모리 모델 저장소
model_store = {
    "trained": False,
    "signals": [],
    "stats": {"total": 0, "mae": None, "last_trained": None}
}

def simple_predict(signal_score, avg_drop):
    """간단한 통계 기반 예측 (모델 없을 때 fallback)"""
    confidence = min(90, max(50, int(signal_score * 0.8)))
    expected_drop = -(avg_drop or 10)
    return {"drop_pct": expected_drop, "confidence": confidence, "method": "statistical"}

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_trained": model_store["trained"],
                    "signals_count": len(model_store["signals"])})

@app.route("/train", methods=["POST"])
def train():
    try:
        data = request.get_json()
        signals = data.get("signals", [])
        if not signals:
            return jsonify({"status": "ok", "message": "no data", "total_signals": 0, "buy_mae": None})

        model_store["signals"] = signals
        model_store["trained"] = True

        # 간단 통계 집계
        drops = [abs(r["actualChange"]) for s in signals
                 for r in (s.get("results") or [])
                 if r.get("actualChange") is not None and r["actualChange"] < 0]
        mae = round(sum(drops) / len(drops), 2) if drops else None

        model_store["stats"] = {
            "total": len(signals),
            "mae": mae,
            "last_trained": datetime.now().isoformat()
        }
        return jsonify({"status": "ok", "total_signals": len(signals), "buy_mae": mae})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        score = data.get("score", 50)
        avg_drop = data.get("avgDrop", 10)
        fig_id = data.get("figId")

        # 학습 데이터 기반 인물별 평균 급락폭 계산
        if model_store["signals"] and fig_id:
            relevant = [s for s in model_store["signals"] if s.get("figureId") == fig_id]
            if relevant:
                drops = [abs(r["actualChange"]) for s in relevant
                         for r in (s.get("results") or [])
                         if r.get("actualChange") is not None and r["actualChange"] < 0]
                if len(drops) >= 3:
                    avg_drop = round(sum(drops) / len(drops), 1)

        result = simple_predict(score, avg_drop)
        result["figId"] = fig_id
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stats", methods=["GET"])
def stats():
    return jsonify(model_store["stats"])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
