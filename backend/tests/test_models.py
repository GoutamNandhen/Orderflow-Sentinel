import joblib
import pytest
from types import SimpleNamespace
from backend.train.train_models import train, generate
from backend.engine import classifier


def test_actual_training_loading_predictions_and_failure_preserves_previous(
    tmp_path, monkeypatch
):
    report = train(tmp_path)
    assert report["dataset_size"] == 5000 and report["splits"] == {
        "training": 3500,
        "validation": 750,
        "test": 750,
    }
    assert sum(c["all"] for c in report["class_counts"].values()) == 5000
    assert 0 <= report["failure_metrics"]["roc_auc"] <= 1
    assert 0 <= report["class_metrics"]["accuracy"] <= 1
    monkeypatch.setattr(classifier, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(classifier, "_bundle", None)
    monkeypatch.setattr(classifier, "_version", None)
    order = SimpleNamespace(
        gateway="DemoShip",
        payment_method="UPI",
        category="Food",
        amount=23500,
        attempt_count=0,
        created_at="2026-10-30T10:00:00+00:00",
        distance_km=3.0,
    )
    result = classifier.predict(order, "API_TIMEOUT", 1, 99)
    assert result["version"] == report["version"]
    assert 0 <= result["failure_probability"] <= 1 and 0 <= result["confidence"] <= 1
    assert isinstance(result["anomaly_raw"], float)
    pointer = (tmp_path / "current.txt").read_text()
    from xgboost import XGBClassifier

    def fail(*args, **kwargs):
        raise RuntimeError("Intentional training failure test")

    monkeypatch.setattr(XGBClassifier, "fit", fail)
    with pytest.raises(RuntimeError):
        train(tmp_path)
    assert (tmp_path / "current.txt").read_text() == pointer
    assert joblib.load(tmp_path / f"{pointer}.joblib")["version"] == pointer


def test_reproducible_synthetic_data():
    one = generate(42)
    two = generate(42)
    assert one[0].equals(two[0])
    assert (one[1] == two[1]).all() and (one[2] == two[2]).all()
