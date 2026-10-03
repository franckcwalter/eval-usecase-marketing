"""Réentraîne un modèle candidat sur l'historique enrichi des résultats de campagne, sans toucher au modèle servi."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from loguru import logger

from evaluation.core import decide, log_run, metrics, record_ids
from training.pipeline import FEATURES, TARGET, TARGET_MAPPING, build_pipeline, tranches_test

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "bank-additional-full.csv"
REFERENCE_PATH = ROOT / "evaluation" / "reference.csv"
GOLDEN_PATH = ROOT / "evaluation" / "golden.json"
SERVED_DIR = ROOT / "models"
CANDIDATES_DIR = ROOT / "models" / "candidates"
NEW_RESULTS_SHARE = 0.10


def history() -> pd.DataFrame:
    data = pd.read_csv(HISTORY_PATH, sep=";").drop_duplicates()
    reference_ids = set(pd.read_csv(REFERENCE_PATH)["_record_id"])
    return data.loc[~record_ids(data).isin(reference_ids)]


def unused_results(database: Path) -> pd.DataFrame:
    with sqlite3.connect(database) as con:
        return pd.read_sql_query("""
            SELECT f.client_id, f.campaign_id, f.true_label, p.features
            FROM feedbacks f JOIN predictions p USING (client_id, campaign_id)
            WHERE f.training_run_id IS NULL
        """, con)


def volume_threshold() -> int:
    return round(len(history()) * NEW_RESULTS_SHARE)


def retrain(database: Path, trigger: str) -> dict:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = unused_results(database)
    new_rows = pd.DataFrame([json.loads(value) for value in results["features"]], columns=FEATURES)
    old = history()
    X = pd.concat([old[FEATURES], new_rows], ignore_index=True)
    y = pd.concat([old[TARGET].map(TARGET_MAPPING), results["true_label"]], ignore_index=True)
    candidate = build_pipeline().fit(X, y)

    reference = pd.read_csv(REFERENCE_PATH)
    y_reference = reference[TARGET].map(TARGET_MAPPING)
    candidate_scores = candidate.predict_proba(reference[FEATURES])[:, 1]
    candidate_metrics = metrics(y_reference, candidate_scores)
    served_metrics = metrics(y_reference, joblib.load(SERVED_DIR / "pipeline.joblib").predict_proba(reference[FEATURES])[:, 1])
    decision = decide(candidate_metrics, served_metrics, json.loads(GOLDEN_PATH.read_text()))

    output = CANDIDATES_DIR / run_id
    output.mkdir(parents=True)
    joblib.dump(candidate, output / "pipeline.joblib", compress=3)
    meta = {**json.loads((SERVED_DIR / "pipeline.json").read_text()), "model_version": f"candidate-{run_id}",
            "created_at": run_id, "trigger": trigger, "n_history": len(old), "n_new_results": len(results),
            "metrics_test": candidate_metrics, "tranches_test": tranches_test(y_reference, candidate_scores)}
    (output / "pipeline.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    summary = {"run_id": run_id, "trigger": trigger, "n_history": len(old), "n_new_results": len(results),
               "candidate": candidate_metrics, "served": served_metrics, **decision}
    try:
        summary["mlflow_run_id"] = log_run(
            "bank-marketing-retraining", run_id,
            {"trigger": trigger, "n_history": len(old), "n_new_results": len(results), "accepted": decision["accepted"]},
            {**{f"candidate_{key}": value for key, value in candidate_metrics.items()},
             **{f"served_{key}": value for key, value in served_metrics.items()}},
            summary,
        )
    except Exception:
        logger.exception("Le réentraînement n’a pas pu être enregistré dans MLflow")
        summary["mlflow_run_id"] = None
    with sqlite3.connect(database) as con:
        con.executemany(
            "UPDATE feedbacks SET training_run_id = ? WHERE client_id = ? AND campaign_id = ?",
            [(run_id, client, campaign) for client, campaign in zip(results["client_id"], results["campaign_id"])],
        )
        con.execute("INSERT INTO retrainings VALUES (?, ?, ?)", (run_id, json.dumps(summary, ensure_ascii=False), run_id))
    return summary
