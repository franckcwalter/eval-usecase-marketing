import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier

from evaluation.core import decide, metrics
from scripts.evaluate_model import evaluate

GOLDEN = Path("evaluation/golden.json")
REFERENCE = Path("evaluation/reference.csv")


def test_unchanged_model_matches_golden(monkeypatch):
    monkeypatch.setattr("scripts.evaluate_model.log_run", lambda *args: "test-run")
    report = evaluate(Path("models"), Path("evaluation/champion"), REFERENCE, GOLDEN)
    assert report["accepted"]
    assert report["candidate"] == report["golden"]
    assert report["gain_vs_champion"] == {"rappel_top50": 0, "roc_auc": 0}


def test_degraded_candidate_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.evaluate_model.log_run", lambda *args: "test-run")
    frame = pd.read_csv(REFERENCE)
    model = DummyClassifier(strategy="prior").fit(frame, frame.y.map({"no": 0, "yes": 1}))
    joblib.dump(model, tmp_path / "pipeline.joblib")
    meta = json.loads(Path("models/pipeline.json").read_text())
    meta["model_version"] = "degraded-test"
    (tmp_path / "pipeline.json").write_text(json.dumps(meta))
    report = evaluate(tmp_path, Path("models"), REFERENCE, GOLDEN)
    assert not report["accepted"]
    assert any("80 %" in reason for reason in report["reasons"])
    assert report["candidate"]["roc_auc"] == .5


def test_changed_reference_is_rejected(tmp_path):
    changed = tmp_path / "reference.csv"
    changed.write_bytes(REFERENCE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="modifié"):
        evaluate(Path("models"), Path("models"), changed, GOLDEN)


def test_policy_checks_champion_and_absolute_floor():
    golden = {"metrics": {"rappel_top50": .82, "roc_auc": .79}, "max_drop": {"rappel_top50": .025, "roc_auc": .018}}
    assert decide({"rappel_top50": .82, "roc_auc": .79}, golden["metrics"], golden, model_changed=False)["accepted"]
    assert decide({"rappel_top50": .85, "roc_auc": .79}, golden["metrics"], golden)["accepted"]
    assert not decide({"rappel_top50": .83, "roc_auc": .80}, golden["metrics"], golden)["accepted"]
    assert not decide({"rappel_top50": .82, "roc_auc": .79}, golden["metrics"], golden)["accepted"]
    assert not decide({"rappel_top50": .79, "roc_auc": .80}, golden["metrics"], golden)["accepted"]
    assert not decide({"rappel_top50": .81, "roc_auc": .77}, golden["metrics"], golden)["accepted"]
    assert not decide({"rappel_top50": .82, "roc_auc": .80}, {"rappel_top50": .90, "roc_auc": .80}, golden)["accepted"]






def test_metrics_require_both_labels():
    with pytest.raises(ValueError):
        metrics([0, 0], [.2, .3])






def test_cli_returns_failure_for_degraded_candidate(tmp_path):
    import os
    import subprocess
    import sys
    frame = pd.read_csv(REFERENCE)
    model = DummyClassifier(strategy="prior").fit(frame.head(100), frame.y.head(100).map({"no": 0, "yes": 1}))
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    joblib.dump(model, candidate / "pipeline.joblib")
    meta = json.loads(Path("models/pipeline.json").read_text())
    meta["model_version"] = "degraded-cli-test"
    (candidate / "pipeline.json").write_text(json.dumps(meta))
    report = tmp_path / "decision.json"
    env = dict(os.environ, MLFLOW_TRACKING_URI=f"sqlite:///{tmp_path / 'mlflow.db'}", MLFLOW_DISABLE_AGENT_HINT="1")
    result = subprocess.run([sys.executable, "-m", "scripts.evaluate_model", "--candidate-dir", str(candidate), "--report", str(report)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    decision = json.loads(report.read_text())
    assert not decision["accepted"]
    assert any("80 %" in reason for reason in decision["reasons"])
