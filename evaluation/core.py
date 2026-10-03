"""Évalue deux modèles sur les mêmes clients et justifie les seuils."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(y, scores):
    y, scores = np.asarray(y, dtype=int), np.asarray(scores, dtype=float)
    if len(y) != len(scores) or len(y) < 2 or set(y) != {0, 1}:
        raise ValueError("L’évaluation exige des labels 0 et 1 et des scores appariés")
    if not np.isfinite(scores).all() or not ((scores >= 0) & (scores <= 1)).all():
        raise ValueError("Scores invalides")
    selected = np.argsort(-scores, kind="stable")[:len(y) // 2]
    return {"rappel_top50": float(y[selected].sum() / y.sum()),
            "roc_auc": float(roc_auc_score(y, scores)),
            "subscription_top50": float(y[selected].mean())}


def bootstrap(y, scores, iterations=500):
    y, scores = np.asarray(y), np.asarray(scores)
    rng = np.random.default_rng(42)
    samples = []
    for _ in range(iterations):
        indices = rng.integers(0, len(y), len(y))
        if len(np.unique(y[indices])) == 2:
            samples.append(metrics(y[indices], scores[indices]))
    if len(samples) < 2:
        raise ValueError("Effectifs insuffisants pour estimer les tolérances")
    return {key: float(2 * np.std([row[key] for row in samples])) for key in ("rappel_top50", "roc_auc")}


def decide(candidate, champion, golden, model_changed=True):
    violations = []
    if candidate["rappel_top50"] < .8:
        violations.append("Rappel à 50 % inférieur à l’objectif métier de 80 %")
    for key in ("rappel_top50", "roc_auc"):
        tolerance = golden["max_drop"][key]
        for name, reference in (("golden run", golden["metrics"]), ("modèle actuel", champion)):
            drop = reference[key] - candidate[key]
            if drop > tolerance + 1e-12:
                violations.append(f"{key} : baisse de {drop:.4f} contre {name}, tolérance {tolerance:.4f}")
    # Le gain minimum vaut la tolérance : un écart plus petit peut venir du hasard de l'échantillon.
    gain, minimum = candidate["rappel_top50"] - champion["rappel_top50"], golden["max_drop"]["rappel_top50"]
    if model_changed and gain < minimum:
        violations.append(f"Gain de rappel à 50 % de {gain * 100:.2f} points, sous le gain minimum de {minimum * 100:.2f} points".replace(".", ","))
    return {"accepted": not violations, "reasons": violations or ["Objectif métier et non-régression respectés"],
            "gain_vs_champion": {key: candidate[key] - champion[key] for key in ("rappel_top50", "roc_auc")}}


def tracking_uri():
    return os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{ROOT / 'mlflow.db'}")


def log_run(experiment, name, params, values, report):
    import mlflow
    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics({key: value for key, value in values.items() if value is not None})
        mlflow.log_dict(report, "report.json")
        return run.info.run_id


def record_ids(frame):
    columns = sorted(column for column in frame.columns if not column.startswith("_"))
    return frame[columns].apply(lambda row: hashlib.sha256(
        json.dumps(row.to_dict(), sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest(), axis=1)
