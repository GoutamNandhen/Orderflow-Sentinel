"""Reproducible synthetic benchmark. No operator approval is an outcome label."""

import argparse
import json
import os
from pathlib import Path
import uuid
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
    roc_auc_score,
    brier_score_loss,
    confusion_matrix,
)
from xgboost import XGBClassifier
from ..db import ROOT, stamp
from ..schemas import ERRORS

CATEGORICAL = ["error_code", "gateway", "payment_method", "category"]
NUMERIC = [
    "http_status",
    "amount",
    "attempt_count",
    "hour",
    "stock_level",
    "distance_km",
]
FEATURES = CATEGORICAL + NUMERIC
ANOMALY_FEATURES = [
    "response_time_ms",
    "gateway_errors_1min",
    "retries",
    "amount",
    "hour",
]
CLASSES = ["NONE"] + ERRORS
HTTP = {
    "NONE": 200,
    "API_TIMEOUT": 504,
    "RATE_LIMIT": 429,
    "TOKEN_EXPIRED": 401,
    "ADDRESS_REJECTED": 422,
    "PAYMENT_DECLINED": 402,
    "UNMATCHED_DEBIT": 202,
    "DUPLICATE_ORDER": 409,
    "OUT_OF_STOCK": 409,
    "STORE_CLOSED": 503,
    "RIDER_LATE": 200,
}


def generate(seed=42, count=5000):
    rng = np.random.default_rng(seed)
    labels = rng.choice(len(CLASSES), count, p=[0.40] + [0.06] * 10)
    codes = np.array(CLASSES)[labels]
    frame = pd.DataFrame(
        {
            "error_code": codes,
            "http_status": [HTTP[c] for c in codes],
            "gateway": rng.choice(
                ["DemoPay Primary", "DemoPay Backup", "DemoShip"], count
            ),
            "payment_method": rng.choice(["UPI", "CARD", "WALLET", "COD"], count),
            "category": rng.choice(
                ["Medicines", "Baby Food", "Food", "Electronics", "Clothes", "Mixed"],
                count,
            ),
            "amount": np.round(rng.lognormal(6.5, 1, count), 2),
            "attempt_count": rng.integers(0, 4, count),
            "hour": rng.integers(0, 24, count),
            "stock_level": rng.integers(0, 101, count),
            "distance_km": rng.uniform(0.5, 15, count),
        }
    )
    # Predict unresolved initial service fault 5 minutes after this observation,
    # assuming normal recovery policy. Stochastic latent service outcome, no future features.
    base = np.array(
        [0.025, 0.12, 0.18, 0.09, 0.75, 0.62, 0.82, 0.70, 0.65, 0.70, 0.55]
    )[labels]
    probabilities = np.clip(
        base + 0.04 * frame.attempt_count + 0.05 * (frame.distance_km > 10), 0.01, 0.98
    )
    target = (rng.random(count) < probabilities).astype(int)
    # Classification includes noisy observable signals, avoiding a perfect lookup benchmark.
    noisy = rng.random(count) < 0.05
    frame.loc[noisy, "error_code"] = rng.choice(CLASSES, noisy.sum())
    frame.loc[noisy, "http_status"] = rng.choice(list(HTTP.values()), noisy.sum())
    anomaly = pd.DataFrame(
        {
            "response_time_ms": np.where(
                labels == 0, rng.uniform(80, 700, count), rng.uniform(800, 12000, count)
            ),
            "gateway_errors_1min": np.where(
                labels == 0, rng.poisson(0.3, count), rng.poisson(3, count)
            ),
            "retries": frame.attempt_count,
            "amount": frame.amount,
            "hour": frame.hour,
        }
    )
    return frame, target, labels, anomaly


def train(artifact_dir=None, seed=42):
    destination = Path(artifact_dir or ROOT / "backend" / "data" / "models")
    destination.mkdir(parents=True, exist_ok=True)
    frame, fail, labels, anomalies = generate(seed)
    indexes = np.arange(len(frame))
    train_idx, remainder = train_test_split(
        indexes, test_size=0.30, random_state=seed, stratify=labels
    )
    validation_idx, test_idx = train_test_split(
        remainder, test_size=0.5, random_state=seed + 1, stratify=labels[remainder]
    )
    preprocessing = ColumnTransformer(
        [
            (
                "category",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL,
            ),
            ("numeric", "passthrough", NUMERIC),
        ]
    )
    x_train = preprocessing.fit_transform(frame.iloc[train_idx])
    x_validation = preprocessing.transform(frame.iloc[validation_idx])
    x_test = preprocessing.transform(frame.iloc[test_idx])
    params = dict(
        n_estimators=180,
        max_depth=3,
        learning_rate=0.06,
        subsample=0.9,
        colsample_bytree=0.9,
        tree_method="hist",
        n_jobs=2,
        random_state=seed,
        early_stopping_rounds=15,
    )
    failure = XGBClassifier(**params, eval_metric="logloss")
    failure.fit(
        x_train,
        fail[train_idx],
        eval_set=[(x_validation, fail[validation_idx])],
        verbose=False,
    )
    classifier = XGBClassifier(
        **params,
        objective="multi:softprob",
        num_class=len(CLASSES),
        eval_metric="mlogloss",
    )
    classifier.fit(
        x_train,
        labels[train_idx],
        eval_set=[(x_validation, labels[validation_idx])],
        verbose=False,
    )
    scaler = StandardScaler().fit(anomalies.iloc[train_idx][labels[train_idx] == 0])
    isolation = IsolationForest(
        n_estimators=150, contamination=0.04, random_state=seed, n_jobs=2
    )
    isolation.fit(scaler.transform(anomalies.iloc[train_idx][labels[train_idx] == 0]))
    fail_probs = failure.predict_proba(x_test)[:, 1]
    class_probs = classifier.predict_proba(x_test)
    version = stamp().replace(":", "").replace("+", "_") + "-" + uuid.uuid4().hex[:6]
    report = {
        "version": version,
        "trained_at": stamp(),
        "seed": seed,
        "dataset_size": len(frame),
        "splits": {
            "training": len(train_idx),
            "validation": len(validation_idx),
            "test": len(test_idx),
        },
        "class_counts": {
            name: {
                "all": int((labels == i).sum()),
                "test": int((labels[test_idx] == i).sum()),
            }
            for i, name in enumerate(CLASSES)
        },
        "failure_target": "Initial service fault remains unresolved 5 minutes after prediction, under the synthetic normal recovery policy.",
        "failure_metrics": {
            "roc_auc": float(roc_auc_score(fail[test_idx], fail_probs)),
            "brier_score": float(brier_score_loss(fail[test_idx], fail_probs)),
            "log_loss": float(log_loss(fail[test_idx], fail_probs)),
            "accuracy": float(accuracy_score(fail[test_idx], fail_probs >= 0.5)),
        },
        "class_metrics": {
            "accuracy": float(accuracy_score(labels[test_idx], class_probs.argmax(1))),
            "macro_f1": float(
                f1_score(labels[test_idx], class_probs.argmax(1), average="macro")
            ),
            "log_loss": float(log_loss(labels[test_idx], class_probs)),
            "confusion_matrix": confusion_matrix(
                labels[test_idx], class_probs.argmax(1)
            ).tolist(),
        },
        "features": FEATURES,
        "anomaly_features": ANOMALY_FEATURES,
        "usable_labelled_feedback": 0,
        "feedback_note": "Operator preferences are recorded separately. No independently verified outcome labels exist; feedback is excluded from training.",
        "limitations": [
            "Synthetic distribution only; no production accuracy claim.",
            "Error signals strongly identify the simulated class; classification accuracy is not action safety.",
            "Probabilities are uncalibrated synthetic estimates.",
            "Isolation Forest trains on healthy training observations only; decision_function < 0 is anomalous. Raw output is preserved; display normalization = clip(0.5 - raw, 0, 1).",
            "Validation selects early stopping; test data is untouched until evaluation. All preprocessing fits training only.",
        ],
    }
    bundle = {
        "version": version,
        "preprocessing": preprocessing,
        "failure": failure,
        "classifier": classifier,
        "isolation": isolation,
        "scaler": scaler,
        "classes": CLASSES,
        "report": report,
    }
    # Publish pointer last; a failed training run cannot remove the previous usable model.
    joblib.dump(bundle, destination / f"{version}.joblib")
    (destination / f"{version}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    temporary = destination / "current.tmp"
    temporary.write_text(version, encoding="utf-8")
    os.replace(temporary, destination / "current.txt")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(json.dumps(train(seed=args.seed), indent=2))
