"""Entraîne le modèle retenu et le sauvegarde pour l'API.

Usage, depuis la racine du repo :
    python -m training.train

Sorties :
    models/pipeline.joblib   pipeline complet (préprocessing + modèle)
    models/pipeline.json     métadonnées de traçabilité
    mlflow.db, mlruns/       run MLflow (paramètres, métriques, modèle)
"""
import json
import platform
import subprocess
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from training.pipeline import (
    CATEGORICAL_FEATURES, FEATURES, HYPERPARAMETERS, NUMERIC_FEATURES,
    RANDOM_STATE, SCENARIO, TARGET, TARGET_MAPPING, build_pipeline, tranches_test,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "bank-additional-full.csv"
MODELS_DIR = ROOT / "models"
MODEL_NAME = "bank_marketing_s5_logreg"
MODEL_VERSION = "1.0.0"


def rappel_selection(y_vrai, probas, proportion):
    """Part des souscripteurs retrouvés parmi la proportion de clients au score le plus élevé."""
    selection = np.argsort(-probas, kind="stable")[: int(len(probas) * proportion)]
    return np.asarray(y_vrai)[selection].sum() / np.asarray(y_vrai).sum()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "non disponible"


def main() -> None:
    df = pd.read_csv(DATA_PATH, sep=";").drop_duplicates()
    X = df.drop(columns=[TARGET])
    y = df[TARGET].map(TARGET_MAPPING)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    pipeline = build_pipeline().fit(X_train, y_train)
    probas = pipeline.predict_proba(X_test)[:, 1]
    metrics = {
        **{f"rappel_top{int(p * 100)}": rappel_selection(y_test, probas, p) for p in (0.25, 0.30, 0.50, 0.75)},
        "roc_auc": roc_auc_score(y_test, probas),
    }

    mlflow.set_tracking_uri(f"sqlite:///{ROOT / 'mlflow.db'}")
    mlflow.set_experiment("bank-marketing")
    with mlflow.start_run(run_name=f"{SCENARIO}-logreg") as run:
        mlflow.log_params({"scenario": SCENARIO, **HYPERPARAMETERS})
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(
            sk_model=pipeline,
            name="model",
            input_example=X_train[FEATURES].head(3),
            skops_trusted_types=["training.pipeline.regrouper_default"],
        )

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(pipeline, MODELS_DIR / "pipeline.joblib", compress=3)
    meta = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "scenario": SCENARIO,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "mlflow_run_id": run.info.run_id,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "dataset_sha256": sha256(DATA_PATH.read_bytes()).hexdigest(),
        "hyperparameters": HYPERPARAMETERS,
        "metrics_test": {name: round(value, 4) for name, value in metrics.items()},
        "tranches_test": tranches_test(y_test, probas),
        "features": {"numeric": NUMERIC_FEATURES, "categorical": CATEGORICAL_FEATURES},
        "target": {"column": TARGET, "mapping": TARGET_MAPPING},
    }
    (MODELS_DIR / "pipeline.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta["metrics_test"], indent=2))


if __name__ == "__main__":
    main()
