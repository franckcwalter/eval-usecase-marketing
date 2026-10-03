"""Évalue les résultats confirmés sans inventer les labels manquants."""
import json
import sqlite3

import pandas as pd
from scipy.stats import beta


def read_campaigns(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
        predictions = pd.read_sql_query("""
            SELECT p.*, f.true_label, f.training_run_id, c.client_id IS NOT NULL AS called,
                   COALESCE(s.closed, 0) AS closed
            FROM predictions p
            LEFT JOIN feedbacks f USING (client_id, campaign_id)
            LEFT JOIN campaign_calls c USING (client_id, campaign_id)
            LEFT JOIN campaigns s USING (campaign_id)
        """, con)
    return predictions


def evaluate_campaign(frame):
    called = frame.loc[frame.called.astype(bool)]
    known = called.loc[called.true_label.notna()]
    complete = len(called) > 0 and len(known) == len(called)
    closed = bool(frame.closed.all())
    # La tranche d'un profil individuel ne définit pas sa sélection dans une campagne.
    selection = frame.loc[(frame.tranche_method == "batch_rank") & (frame.tranche.str.split("-").str[0].astype(int) < 50)]
    selected = selection.loc[selection.called.astype(bool)]
    labelled = selected.loc[selected.true_label.notna()]
    n, successes = len(labelled), int(labelled.true_label.sum())
    rate = successes / n if n else None
    ready = closed and complete and len(selection) > 0 and len(selected) == len(selection)
    bounds = None
    if n:
        bounds = [0.0 if successes == 0 else float(beta.ppf(.025, successes, n - successes + 1)),
                  1.0 if successes == n else float(beta.ppf(.975, successes + 1, n - successes))]
    tranches = []
    for (method, tranche), group in known.groupby(["tranche_method", "tranche"], sort=True):
        tranches.append({"method": method, "tranche": tranche, "n": len(group),
                         "observed_rate": float(group.true_label.mean()),
                         "displayed_rate": float(group.displayed_rate.mean()),
                         "gap": float(group.true_label.mean() - group.displayed_rate.mean())})
    return {"period_start": str(frame.created_at.min()), "period_end": str(frame.created_at.max()),
            "scored": len(frame), "called": len(called), "known": len(known),
            "coverage": len(known) / len(called) if len(called) else None,
            "closed": closed, "complete": complete, "evaluable": ready,
            "selected_expected": len(selection), "selected_called": len(selected), "selected_known": n,
            "subscriptions": successes, "subscription_rate": rate,
            "confidence_interval_95": bounds, "threshold": .18,
            "alert": ready and rate < .18, "provisional": not ready,
            "tranches": tranches,
            "model_versions": sorted(frame.model_version.unique().tolist()),
            "global_recall": None, "concept_drift": "human_diagnosis_required"}


def features(frame):
    return pd.DataFrame([json.loads(value) for value in frame.features])
