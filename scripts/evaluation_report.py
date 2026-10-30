"""Export the active measured model report into reviewable documentation."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
models = root / 'backend/data/models'
version = (models / 'current.txt').read_text(encoding='utf-8').strip()
report = json.loads((models / f'{version}.json').read_text(encoding='utf-8'))
(root / 'docs/model-evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
lines = ['# Measured synthetic model evaluation', '', f'Active version: `{version}`', '',
    f'Trained at {report["trained_at"]} (UTC). Seed {report["seed"]}. Dataset: {report["dataset_size"]:,} reproducible synthetic observations.', '',
    '## Experimental design', '', report['failure_target'], '',
    'Stratified split: 3,500 training / 750 validation / 750 test. One-hot preprocessing and anomaly standardisation fit training rows only. Validation controls XGBoost early stopping. Test rows are evaluated once after fitting. CPU histogram trees, two threads; no GPU.', '',
    'Features at observation time: ' + ', '.join(f'`{f}`' for f in report['features']) + '.', '',
    'Isolation Forest features: ' + ', '.join(f'`{f}`' for f in report['anomaly_features']) + '.', '',
    'The stochastic failure target uses error type, attempt count and distance as observable causes of a future unresolved outcome. The classification target is the simulated initial cause, including NONE, with 5% noisy observable error/status signals. No resolution time, approval decision, chosen action, future debit outcome or future delivery event is a prediction feature.', '',
    '## Held-out test metrics', '', '| Model | Metric | Measured value |', '|---|---|---|']
for kind, key in [('Failure probability', 'failure_metrics'), ('Error class', 'class_metrics')]:
    for metric, value in report[key].items():
        if isinstance(value, (float, int)):
            lines.append(f'| {kind} | {metric} | {value:.8f} |')
lines += ['', 'The maximum error-class probability is exposed as confidence, separately from failure probability. These are uncalibrated synthetic estimates. Class confidence cannot authorize unsafe or irreversible actions by itself.', '',
    '## Class counts', '', '| Class | All data | Held-out test |', '|---|---:|---:|']
for name, count in report['class_counts'].items():
    lines.append(f'| {name} | {count["all"]} | {count["test"]} |')
lines += ['', '## Artifacts and fallback', '',
    'Each version saves a joblib bundle containing fitted preprocessing, both XGBoost models, Isolation Forest, anomaly scaler, classes, seed, features and report; the JSON sidecar preserves the evaluation. `current.txt` is atomically replaced only after successful training. A failed run preserves the previous pointer. Before training, rules detect errors and policy uses worst-case uncertainty; model probabilities are explicitly unavailable.', '',
    'Raw anomaly output is sklearn `decision_function`; negative means anomalous. The UI also exposes the documented optional display normalization `clip(0.5 - raw, 0, 1)`. The raw output is not relabelled a probability.', '',
    f'Usable independently labelled operator feedback: **{report["usable_labelled_feedback"]}**. ' + report['feedback_note'], '', '## Limitations', '']
lines += ['- ' + item for item in report['limitations']]
lines += ['', 'The full measured confusion matrix, complete feature schema, class counts and version metadata are in `model-evaluation.json`. Reproduce with `python -m backend.train.train_models --seed 42`, then `python scripts/evaluation_report.py`.', '',
    'Implementation references: [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/), [XGBoost Python API](https://xgboost.readthedocs.io/en/stable/python/python_api.html).']
(root / 'docs/MODEL_EVALUATION.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(version)
