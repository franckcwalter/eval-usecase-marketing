"""Bloque une publication qui viole les garde-fous du jeu de référence."""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd

from evaluation.core import ROOT, decide, digest, log_run, metrics
from training.pipeline import FEATURES


def evaluate(candidate_dir, champion_dir, reference, golden_path, release_tag="local"):
    golden = json.loads(Path(golden_path).read_text())
    if digest(reference) != golden["reference_sha256"]:
        raise ValueError("Le jeu de référence a été modifié")
    frame = pd.read_csv(reference)
    y = frame.y.map({"no": 0, "yes": 1})
    if y.isna().any():
        raise ValueError("Labels inconnus dans le jeu de référence")
    results, versions = {}, {}
    reference_ids = set(frame._record_id) | {hashlib.sha256(str(value).encode()).hexdigest() for value in frame._record_id}
    for name, directory in (("candidate", Path(candidate_dir)), ("champion", Path(champion_dir))):
        meta = json.loads((directory / "pipeline.json").read_text())
        if set(meta.get("training_record_ids", [])) & reference_ids:
            raise ValueError("Des clients de référence ont été utilisés pour entraîner le candidat")
        required = meta["features"]["numeric"] + meta["features"]["categorical"]
        if not set(required) <= set(FEATURES):
            raise ValueError("Le candidat demande des variables absentes du contrat de l’API")
        model = joblib.load(directory / "pipeline.joblib")
        results[name] = metrics(y, model.predict_proba(frame)[:, 1])
        versions[name] = meta["model_version"]
    model_changed = digest(Path(candidate_dir) / "pipeline.joblib") != digest(Path(champion_dir) / "pipeline.joblib")
    decision = decide(results["candidate"], results["champion"], golden, model_changed)
    report = {**decision, **results, "golden": golden["metrics"], "versions": versions,
              "reference_sha256": digest(reference), "release_tag": release_tag}
    report["mlflow_run_id"] = log_run("bank-marketing-ci", release_tag, {
        **{f"{key}_version": value for key, value in versions.items()},
        "reference_sha256": digest(reference), "accepted": decision["accepted"],
    }, {f"{model}_{key}": value for model, values in results.items() for key, value in values.items()}, report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--champion-dir", type=Path, default=ROOT / "evaluation" / "champion")
    parser.add_argument("--reference", type=Path, default=ROOT / "evaluation" / "reference.csv")
    parser.add_argument("--golden", type=Path, default=ROOT / "evaluation" / "golden.json")
    parser.add_argument("--release-tag", default="local")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "evaluation.json")
    args = parser.parse_args()
    try:
        report = evaluate(args.candidate_dir, args.champion_dir, args.reference, args.golden, args.release_tag)
    except Exception as exc:
        report = {"accepted": False, "reasons": [str(exc)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
