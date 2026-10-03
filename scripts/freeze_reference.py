"""Gèle le jeu de référence et le golden run sans modifier le modèle servi."""
import json
import shutil
from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split

from evaluation.core import ROOT, bootstrap, digest, log_run, metrics, record_ids
from training.pipeline import RANDOM_STATE


def main():
    directory = ROOT / "evaluation"
    baseline = directory / "golden.json"
    reference = directory / "reference.csv"
    if baseline.exists() or reference.exists():
        raise SystemExit("La référence existe déjà ; elle doit rester figée")
    data_path = ROOT / "data" / "bank-additional-full.csv"
    data = pd.read_csv(data_path, sep=";").drop_duplicates()
    meta = json.loads((ROOT / "models" / "pipeline.json").read_text())
    if digest(data_path) != meta["dataset_sha256"]:
        raise SystemExit("Les données historiques ne correspondent pas au modèle actuel")
    _, test = train_test_split(data, test_size=.2, stratify=data.y, random_state=RANDOM_STATE)
    test = test.copy()
    test["_record_id"] = record_ids(test)
    model = joblib.load(ROOT / "models" / "pipeline.joblib")
    scores = model.predict_proba(test)[:, 1]
    y = test.y.map({"no": 0, "yes": 1})
    values = metrics(y, scores)
    tolerance = bootstrap(y, scores)
    test.to_csv(reference, index=False)
    champion = directory / "champion"
    champion.mkdir(exist_ok=True)
    for name in ("pipeline.joblib", "pipeline.json"):
        shutil.copy2(ROOT / "models" / name, champion / name)
    result = {"model_version": meta["model_version"], "model_sha256": digest(champion / "pipeline.joblib"),
              "reference_sha256": digest(reference), "n": len(test), "metrics": values,
              "max_drop": tolerance, "bootstrap_iterations": 500,
              "bootstrap_seed": 42, "reference_role": "historical_non_regression"}
    result["mlflow_run_id"] = log_run("bank-marketing-reference", "golden-run", {
        "model_version": meta["model_version"], "reference_sha256": result["reference_sha256"],
        "n_reference": len(test), "bootstrap_iterations": 500,
    }, values, result)
    baseline.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
