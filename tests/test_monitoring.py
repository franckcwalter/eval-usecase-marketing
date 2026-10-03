import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.main import app
from monitoring.campaigns import evaluate_campaign, read_campaigns
from monitoring.drift import compare, psi
from tests.test_api import post_csv
from training.pipeline import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def ranked_campaign(client, clients_csv):
    assert post_csv(client, clients_csv).status_code == 200
    campaign = clients_csv.campaign_id.iloc[0]
    response = client.post(f"/campaigns/{campaign}/calls", json={"selected_top50": True})
    assert response.status_code == 200
    assert response.json()["called"] == 25
    return campaign


def label_selected(client, campaign, positives):
    frame = read_campaigns(app.state.database_path)
    ids = frame.loc[frame.called.astype(bool)].client_id.tolist()
    for i, cid in enumerate(ids):
        assert client.post("/feedback", json={"client_id": cid, "campaign_id": campaign, "true_label": int(i < positives)}).status_code == 201


def test_provisional_results_do_not_trigger_alert(client, clients_csv):
    campaign = ranked_campaign(client, clients_csv)
    report = evaluate_campaign(read_campaigns(app.state.database_path))
    assert report["subscription_rate"] is None
    assert report["provisional"] and not report["alert"]
    assert client.post(f"/campaigns/{campaign}/close").status_code == 422
    assert report["global_recall"] is None


@pytest.mark.parametrize(("positives", "alert"), [(4, True), (5, False)])
def test_campaign_alert_requires_closed_complete_results(client, clients_csv, positives, alert):
    campaign = ranked_campaign(client, clients_csv)
    label_selected(client, campaign, positives)
    before = evaluate_campaign(read_campaigns(app.state.database_path))
    assert not before["alert"]
    assert before["subscription_rate"] == positives / 25
    response = client.post(f"/campaigns/{campaign}/close")
    assert response.status_code == 200
    assert response.json()["subscription_rate"] == positives / 25
    assert response.json()["below_threshold"] == alert
    tranches = response.json()["tranches"]
    assert sum(row["n"] for row in tranches) == 25
    assert all(set(row) >= {"tranche", "displayed_rate", "observed_rate"} for row in tranches)
    assert f'bank_campaign_subscription_rate{{campaign="{campaign}"}}' in client.get("/metrics").text
    after = evaluate_campaign(read_campaigns(app.state.database_path))
    assert after["evaluable"] and after["alert"] == alert
    assert after["known"] == 25 and after["scored"] == 50
    assert after["coverage"] == 1
    assert after["global_recall"] is None
    assert all(row["method"] == "batch_rank" for row in after["tranches"])
    assert client.post(f"/campaigns/{campaign}/calls", json={"selected_top50": True}).status_code == 409
    assert post_csv(client, clients_csv).status_code == 409


def test_partial_calls_do_not_claim_top50_is_evaluated(client, clients_csv):
    assert post_csv(client, clients_csv).status_code == 200
    frame = read_campaigns(app.state.database_path)
    selected = frame.loc[frame["rank"] == 1].iloc[0]
    assert client.post("/feedback", json={"client_id": selected.client_id, "campaign_id": selected.campaign_id, "true_label": 0}).status_code == 201
    response = client.post(f"/campaigns/{selected.campaign_id}/close")
    assert response.status_code == 200
    assert response.json()["selected_known"] == 1 and response.json()["selected_expected"] == 25
    report = evaluate_campaign(read_campaigns(app.state.database_path))
    assert report["selected_expected"] == 25
    assert report["selected_called"] == 1
    assert not report["evaluable"] and not report["alert"]


def test_drift_compares_file_before_ranking(client, clients_csv):
    content = clients_csv.to_csv(sep=";", index=False).encode()
    response = client.post("/drift", files={"file": ("clients.csv", content, "text/csv")})
    assert response.status_code == 200
    body = response.json()
    assert body["n_clients"] == 50 and body["n_reference"] == 8236
    assert set(row["feature"] for row in body["variables"]) == set(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
    assert read_campaigns(app.state.database_path).empty


def test_ranking_records_drift(client, clients_csv):
    from api.storage import read_drift
    assert post_csv(client, clients_csv).status_code == 200
    assert len(read_drift(app.state.database_path)["campagne-2026-10"]) == 9
    assert client.get("/metrics").text.count('bank_drift_level{campaign="campagne-2026-10"') == 9


def test_drift_rejects_invalid_file(client, clients_csv):
    content = clients_csv.drop(columns="contact").to_csv(sep=";", index=False).encode()
    assert client.post("/drift", files={"file": ("clients.csv", content, "text/csv")}).status_code == 422


def test_psi_handles_constant_reference_and_outliers():
    assert psi([1] * 100, [1] * 100) == pytest.approx(0)
    assert psi([1] * 100, [2] * 100) > .25
    assert psi([1, 2, 3] * 100, [100] * 100) > .25
    assert psi([1, 2], []) is None


def test_sparse_chi2_is_not_reported_as_stable():
    ref = pd.DataFrame({"contact": ["cellular", "telephone"]})
    cur = pd.DataFrame({"contact": ["cellular"]})
    row, = compare(ref, cur, [], ["contact"])
    assert row["chi2_pvalue"] is None
    assert row["status"] == "insufficient_counts"


def test_http_metrics_and_report_endpoint(client):
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert 'route="/health"' in response.text
    assert "bank_http_duration_seconds_bucket" in response.text
    assert "request_id=" not in response.text


def test_unknown_calls_are_rejected_atomically(client, clients_csv):
    assert post_csv(client, clients_csv).status_code == 200
    cid = clients_csv.client_id.iloc[0]
    response = client.post("/campaigns/campagne-2026-10/calls", json={"client_ids": [cid, "inconnu"]})
    assert response.status_code == 422
    assert not read_campaigns(app.state.database_path).called.any()




def test_campaign_finishes_with_feedback_only(client, clients_csv):
    assert post_csv(client, clients_csv).status_code == 200
    frame = read_campaigns(app.state.database_path)
    selected = frame.loc[frame.tranche.str.split("-").str[0].astype(int) < 50]
    campaign = clients_csv.campaign_id.iloc[0]
    for cid in selected.client_id:
        assert client.post("/feedback", json={"client_id": cid, "campaign_id": campaign, "true_label": 0}).status_code == 201
    assert client.post(f"/campaigns/{campaign}/close").status_code == 200
    report = evaluate_campaign(read_campaigns(app.state.database_path))
    assert report["evaluable"] and report["alert"]


def test_degradation_triggers_candidate_training(client, clients_csv, tmp_path):
    campaign = ranked_campaign(client, clients_csv)
    label_selected(client, campaign, 0)
    body = client.post(f"/campaigns/{campaign}/close").json()
    assert body["below_threshold"]
    retraining = body["retraining"]
    assert retraining["trigger"] == "degradation" and retraining["n_new_results"] == 25
    assert retraining["mlflow_run_id"] == "test-run"
    assert set(retraining["candidate"]) >= {"rappel_top50", "roc_auc"}
    assert (tmp_path / "candidates" / retraining["run_id"] / "pipeline.joblib").exists()
    assert Path("models/pipeline.joblib").exists()
    import sqlite3
    with sqlite3.connect(app.state.database_path) as con:
        assert con.execute("SELECT COUNT(*) FROM feedbacks WHERE training_run_id IS NULL").fetchone()[0] == 0


def test_no_training_below_volume_without_degradation(client, clients_csv):
    campaign = ranked_campaign(client, clients_csv)
    label_selected(client, campaign, 10)
    body = client.post(f"/campaigns/{campaign}/close").json()
    assert body["retraining"] is None
    assert body["unused_results"] == 25 and body["retrain_threshold"] == 3294


def test_volume_triggers_training(client, clients_csv, monkeypatch):
    campaign = ranked_campaign(client, clients_csv)
    label_selected(client, campaign, 10)
    monkeypatch.setattr(app.state, "retrain_threshold", 25)
    assert client.post(f"/campaigns/{campaign}/close").json()["retraining"]["trigger"] == "volume"


def test_rejections_are_counted_by_motif(client, clients_csv, valid_payload):
    content = clients_csv.drop(columns="contact").to_csv(sep=";", index=False).encode()
    assert client.post("/rank", files={"file": ("clients.csv", content, "text/csv")}).status_code == 422
    assert client.post("/predict", json={**valid_payload, "previous": -1}).status_code == 422
    text = client.get("/metrics").text
    assert 'bank_rejections_total{motif="colonnes_manquantes",route="/rank"}' in text
    assert 'bank_rejections_total{motif="valeur_invalide",route="/predict"}' in text


def test_out_of_range_clients_are_flagged(client, clients_csv, valid_payload):
    assert client.post("/predict", json=valid_payload).json()["hors_historique"] is False
    outside = {**valid_payload, "client_id": "hors", "cons.conf.idx": -80}
    assert client.post("/predict", json=outside).json()["hors_historique"] is True
    frame = clients_csv.copy()
    frame.loc[frame.index[0], "cons.conf.idx"] = -80
    ranked = pd.read_csv(io.StringIO(post_csv(client, frame).text), sep=";")
    assert (ranked.hors_historique == "oui").sum() == 1
    content = frame.to_csv(sep=";", index=False).encode()
    drift = client.post("/drift", files={"file": ("clients.csv", content, "text/csv")}).json()
    assert drift["outside_clients"] == [frame.client_id.iloc[0]]
