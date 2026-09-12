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

# ── Firestore (영구 저장) 초기화 ──────────────────────────────
# GitHub Actions와 동일한 FIREBASE_SERVICE_ACCOUNT 시크릿을 사용.
# Admin SDK는 Firestore 보안 규칙(write:false)을 우회하므로
# 클라이언트 브라우저에서는 막힌 저장을 서버 경유로 안전하게 수행한다.
_fs_client = None
_fs_init_error = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    _sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if _sa_json:
        _cred = credentials.Certificate(json.loads(_sa_json))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(_cred)
        _fs_client = firestore.client()
    else:
        _fs_init_error = "FIREBASE_SERVICE_ACCOUNT env var not set"
except Exception as e:
    _fs_init_error = str(e)

_BACKUP_COLLECTION = "radar_backup"  # radar/main(자동수집 데이터)과 완전 분리


def simple_predict(signal_score, avg_drop):
    """간단한 통계 기반 예측 (모델 없을 때 fallback)"""
    confidence = min(90, max(50, int(signal_score * 0.8)))
    expected_drop = -(avg_drop or 10)
    return {"drop_pct": expected_drop, "confidence": confidence, "method": "statistical"}

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_trained": model_store["trained"],
        "signals_count": len(model_store["signals"]),
        "firestore_backup": "ok" if _fs_client else f"disabled ({_fs_init_error})",
    })

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


# ── 영구 저장/복원 (프론트엔드 serverSave/serverLoad가 호출) ──────
# 이 라우트가 없어서 그동안 매 저장 시도가 404로 실패하고 있었음.
# Firestore Admin SDK로 radar_backup/{key} 문서에 저장 → 캐시 삭제·
# 기기 변경에도 데이터 보존됨 (radar/main 자동수집 데이터와는 분리).
@app.route("/save", methods=["POST"])
def save_data():
    if not _fs_client:
        return jsonify({"status": "error", "error": f"firestore not configured: {_fs_init_error}"}), 503
    try:
        body = request.get_json(force=True) or {}
        key = body.get("key")
        data = body.get("data")
        if not key:
            return jsonify({"status": "error", "error": "key required"}), 400
        _fs_client.collection(_BACKUP_COLLECTION).document(key).set({
            "data": data,
            "updatedAt": datetime.now().isoformat(),
        })
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/load", methods=["GET"])
def load_data():
    if not _fs_client:
        return jsonify({"status": "error", "error": f"firestore not configured: {_fs_init_error}"}), 503
    try:
        key = request.args.get("key")
        if not key:
            return jsonify({"status": "error", "error": "key required"}), 400
        snap = _fs_client.collection(_BACKUP_COLLECTION).document(key).get()
        if not snap.exists:
            return jsonify({"status": "ok", "data": None})
        return jsonify({"status": "ok", "data": snap.to_dict().get("data")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
