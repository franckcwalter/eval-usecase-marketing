import io
import json
import sqlite3

import pandas as pd
import pytest

from api.main import app
from api.storage import initialize
from tests.test_api import post_csv
from training.pipeline import FEATURES


def rows(table):
    with sqlite3.connect(app.state.database_path) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute(f"SELECT * FROM {table}")]


def outcome(payload, label=1):
    return {key: payload[key] for key in ("client_id", "campaign_id")} | {"true_label": label}


def test_predict_stores_features_without_identifiers(client, valid_payload):
    response = client.post("/predict", json=valid_payload)
    assert response.status_code == 200
    record, = rows("predictions")
    assert record["client_id"] == "000123"
    assert set(json.loads(record["features"])) == set(FEATURES)
    assert record["score"] == response.json()["score"]
    assert record["tranche_method"] == "test_score_bounds"
    assert record["model_version"] == response.json()["model_version"]
    initialize(app.state.database_path)
    assert rows("predictions") == [record]


def test_feedback_replay_conflict_and_join(client, valid_payload):
    client.post("/predict", json=valid_payload)
    first = client.post("/feedback", json=outcome(valid_payload))
    assert first.status_code == 201
    assert first.json()["status"] == "stored"
    assert client.post("/feedback", json=outcome(valid_payload)).json()["status"] == "already_stored"
    assert client.post("/feedback", json=outcome(valid_payload, 0)).status_code == 409
    record, = rows("feedbacks")
    assert record["true_label"] == 1
    assert record["training_run_id"] is None
    with sqlite3.connect(app.state.database_path) as con:
        features, label = con.execute("""
            SELECT p.features, f.true_label FROM predictions p JOIN feedbacks f
            USING (client_id, campaign_id)
        """).fetchone()
    assert json.loads(features)["previous"] == valid_payload["previous"]
    assert label == 1


def test_feedback_requires_matching_campaign(client, valid_payload):
    assert client.post("/feedback", json=outcome(valid_payload)).status_code == 404
    client.post("/predict", json=valid_payload)
    other = outcome(valid_payload) | {"campaign_id": "autre-campagne"}
    assert client.post("/feedback", json=other).status_code == 404
    assert rows("feedbacks") == []


@pytest.mark.parametrize("label", [-1, 2, "1", True, None, 0.5])
def test_feedback_rejects_invalid_label(client, valid_payload, label):
    assert client.post("/feedback", json=outcome(valid_payload, label)).status_code == 422


@pytest.mark.parametrize("field", ["client_id", "campaign_id"])
def test_predict_requires_identifiers(client, valid_payload, field):
    for value in (None, "", "   "):
        assert client.post("/predict", json=valid_payload | {field: value}).status_code == 422
    payload = {key: value for key, value in valid_payload.items() if key != field}
    assert client.post("/predict", json=payload).status_code == 422
    assert rows("predictions") == []


def test_prediction_is_not_overwritten(client, valid_payload):
    assert client.post("/predict", json=valid_payload).status_code == 200
    previous = rows("predictions")
    assert client.post("/predict", json=valid_payload).status_code == 200
    assert client.post("/predict", json=valid_payload | {"previous": 2}).status_code == 409
    assert rows("predictions") == previous
    assert client.post("/predict", json=valid_payload | {"campaign_id": "nouvelle"}).status_code == 200
    assert len(rows("predictions")) == 2


def test_rank_preserves_identifiers_and_links_feedback(client, clients_csv):
    response = post_csv(client, clients_csv)
    assert response.status_code == 200
    ranked = pd.read_csv(io.StringIO(response.text), sep=";", dtype={"client_id": str})
    saved = {row["client_id"]: row for row in rows("predictions")}
    for row in ranked.to_dict("records"):
        record = saved[row["client_id"]]
        assert record["rank"] == row["rang"]
        assert record["score"] == row["score"]
        source = clients_csv.loc[clients_csv.client_id == row["client_id"]].iloc[0]
        assert json.loads(record["features"])["previous"] == int(source["previous"])
        assert record["tranche_method"] == "batch_rank"
    payload = {"client_id": ranked.iloc[-1].client_id, "campaign_id": "campagne-2026-10", "true_label": 0}
    assert client.post("/feedback", json=payload).status_code == 201
    assert rows("feedbacks")[0]["true_label"] == 0


def test_rank_conflict_rolls_back_entire_batch(client, clients_csv):
    assert post_csv(client, clients_csv).status_code == 200
    previous = rows("predictions")
    changed = clients_csv.copy()
    changed.loc[changed.index[0], "client_id"] = "nouveau-client"
    changed.loc[changed.index[-1], "previous"] = 100
    assert post_csv(client, changed).status_code == 409
    assert rows("predictions") == previous


def test_rank_rejects_duplicate_clients_and_mixed_campaigns(client, clients_csv):
    duplicate = pd.concat([clients_csv, clients_csv.iloc[[0]]])
    assert post_csv(client, duplicate).status_code == 422
    mixed = clients_csv.copy()
    mixed.loc[mixed.index[0], "campaign_id"] = "autre"
    assert post_csv(client, mixed).status_code == 422
    for field in ("client_id", "campaign_id"):
        assert post_csv(client, clients_csv.drop(columns=field)).status_code == 422
    assert rows("predictions") == []
