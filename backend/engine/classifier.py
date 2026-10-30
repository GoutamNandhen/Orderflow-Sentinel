from pathlib import Path
import threading
import joblib
import pandas as pd
from ..db import ROOT
from ..train.train_models import HTTP

_bundle, _version = None, None
_lock = threading.Lock()
MODEL_DIR = ROOT / "backend" / "data" / "models"


def current():
    global _bundle, _version
    with _lock:
        try:
            version = (MODEL_DIR / "current.txt").read_text().strip()
            if version != _version:
                candidate = joblib.load(MODEL_DIR / f"{version}.joblib")
                _bundle, _version = candidate, version
        except (OSError, ValueError, EOFError):
            pass
        return _bundle


def predict(order, error_type, gateway_errors, stock_level):
    bundle = current()
    if not bundle:
        return {
            "source": "rule fallback; probability unavailable",
            "version": None,
            "failure_probability": None,
            "error_class": error_type,
            "confidence": None,
            "policy_confidence": 0.0,
            "anomaly_raw": None,
            "anomaly_display": None,
        }
    row = {
        "error_code": error_type,
        "http_status": HTTP[error_type],
        "gateway": order.gateway,
        "payment_method": order.payment_method,
        "category": order.category,
        "amount": order.amount / 100,
        "attempt_count": order.attempt_count,
        "hour": int(order.created_at[11:13]),
        "stock_level": stock_level,
        "distance_km": order.distance_km,
    }
    x = bundle["preprocessing"].transform(pd.DataFrame([row]))
    probs = bundle["classifier"].predict_proba(x)[0]
    anomaly_row = {
        "response_time_ms": 6000 if error_type == "API_TIMEOUT" else 1200,
        "gateway_errors_1min": gateway_errors,
        "retries": order.attempt_count,
        "amount": order.amount / 100,
        "hour": row["hour"],
    }
    raw = float(
        bundle["isolation"].decision_function(
            bundle["scaler"].transform(pd.DataFrame([anomaly_row]))
        )[0]
    )
    return {
        "source": "synthetic-trained XGBoost + Isolation Forest",
        "version": bundle["version"],
        "failure_probability": float(bundle["failure"].predict_proba(x)[0, 1]),
        "error_class": bundle["classes"][int(probs.argmax())],
        "confidence": float(probs.max()),
        "policy_confidence": float(probs.max()),
        "anomaly_raw": raw,
        "anomaly_display": max(0, min(1, 0.5 - raw)),
        "features": row,
        "anomaly_features": anomaly_row,
    }
