# Measured synthetic model evaluation

Active version: `2026-10-30T135343.163392_0000-4b87dd`

Trained at 2026-10-30T13:53:43.163392+00:00 (UTC). Seed 42. Dataset: 5,000 reproducible synthetic observations.

## Experimental design

Initial service fault remains unresolved 5 minutes after prediction, under the synthetic normal recovery policy.

Stratified split: 3,500 training / 750 validation / 750 test. One-hot preprocessing and anomaly standardisation fit training rows only. Validation controls XGBoost early stopping. Test rows are evaluated once after fitting. CPU histogram trees, two threads; no GPU.

Features at observation time: `error_code`, `gateway`, `payment_method`, `category`, `http_status`, `amount`, `attempt_count`, `hour`, `stock_level`, `distance_km`.

Isolation Forest features: `response_time_ms`, `gateway_errors_1min`, `retries`, `amount`, `hour`.

The stochastic failure target uses error type, attempt count and distance as observable causes of a future unresolved outcome. The classification target is the simulated initial cause, including NONE, with 5% noisy observable error/status signals. No resolution time, approval decision, chosen action, future debit outcome or future delivery event is a prediction feature.

## Held-out test metrics

| Model | Metric | Measured value |
|---|---|---|
| Failure probability | roc_auc | 0.85950814 |
| Failure probability | brier_score | 0.14516634 |
| Failure probability | log_loss | 0.45288858 |
| Failure probability | accuracy | 0.80266667 |
| Error class | accuracy | 0.97466667 |
| Error class | macro_f1 | 0.97066590 |
| Error class | log_loss | 0.13135104 |

The maximum error-class probability is exposed as confidence, separately from failure probability. These are uncalibrated synthetic estimates. Class confidence cannot authorize unsafe or irreversible actions by itself.

## Class counts

| Class | All data | Held-out test |
|---|---:|---:|
| NONE | 2023 | 304 |
| API_TIMEOUT | 307 | 46 |
| RATE_LIMIT | 324 | 48 |
| TOKEN_EXPIRED | 287 | 43 |
| ADDRESS_REJECTED | 295 | 44 |
| PAYMENT_DECLINED | 292 | 44 |
| UNMATCHED_DEBIT | 287 | 43 |
| DUPLICATE_ORDER | 298 | 45 |
| OUT_OF_STOCK | 310 | 47 |
| STORE_CLOSED | 290 | 43 |
| RIDER_LATE | 287 | 43 |

## Artifacts and fallback

Each version saves a joblib bundle containing fitted preprocessing, both XGBoost models, Isolation Forest, anomaly scaler, classes, seed, features and report; the JSON sidecar preserves the evaluation. `current.txt` is atomically replaced only after successful training. A failed run preserves the previous pointer. Before training, rules detect errors and policy uses worst-case uncertainty; model probabilities are explicitly unavailable.

Raw anomaly output is sklearn `decision_function`; negative means anomalous. The UI also exposes the documented optional display normalization `clip(0.5 - raw, 0, 1)`. The raw output is not relabelled a probability.

Usable independently labelled operator feedback: **0**. Operator preferences are recorded separately. No independently verified outcome labels exist; feedback is excluded from training.

## Limitations

- Synthetic distribution only; no production accuracy claim.
- Error signals strongly identify the simulated class; classification accuracy is not action safety.
- Probabilities are uncalibrated synthetic estimates.
- Isolation Forest trains on healthy training observations only; decision_function < 0 is anomalous. Raw output is preserved; display normalization = clip(0.5 - raw, 0, 1).
- Validation selects early stopping; test data is untouched until evaluation. All preprocessing fits training only.

The full measured confusion matrix, complete feature schema, class counts and version metadata are in `model-evaluation.json`. Reproduce with `python -m backend.train.train_models --seed 42`, then `python scripts/evaluation_report.py`.

Implementation references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/), [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html).
