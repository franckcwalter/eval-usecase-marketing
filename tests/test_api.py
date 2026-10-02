import io

import joblib
import pandas as pd
import pytest

from api.main import MODEL_PATH


def post_csv(client, frame: pd.DataFrame, sep: str = ";"):
    content = frame.to_csv(sep=sep, index=False).encode()
    return client.post("/rank", files={"file": ("clients.csv", content, "text/csv")})


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_predict_returns_model_probability(client, valid_payload):
    response = client.post("/predict", json=valid_payload)
    assert response.status_code == 200
    expected = joblib.load(MODEL_PATH).predict_proba(pd.DataFrame([valid_payload]))[0, 1]
    assert response.json()["probabilite"] == round(expected, 3)
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_predict_is_deterministic(client, valid_payload):
    first = client.post("/predict", json=valid_payload).json()["probabilite"]
    second = client.post("/predict", json=valid_payload).json()["probabilite"]
    assert first == second


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("contact", "email"), ("poutcome", "maybe"), ("previous", -1), ("cons.price.idx", "abc")],
)
def test_predict_rejects_invalid_value(client, valid_payload, field, bad_value):
    response = client.post("/predict", json={**valid_payload, field: bad_value})
    assert response.status_code == 422
    assert field in response.text


def test_predict_rejects_missing_field(client, valid_payload):
    response = client.post("/predict", json={k: v for k, v in valid_payload.items() if k != "emp.var.rate"})
    assert response.status_code == 422
    assert "emp.var.rate" in response.text


@pytest.mark.parametrize("sep", [";", ","])
def test_rank_sorts_and_adds_columns(client, clients_csv, sep):
    response = post_csv(client, clients_csv, sep)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    ranked = pd.read_csv(io.StringIO(response.text), sep=sep)
    assert len(ranked) == len(clients_csv)
    assert set(clients_csv.columns) <= set(ranked.columns)
    assert ranked["probabilite"].is_monotonic_decreasing
    assert ranked["rang"].tolist() == list(range(1, len(ranked) + 1))
    assert ranked["tranche"].value_counts().tolist() == [5] * 10


def test_rank_rejects_missing_column(client, clients_csv):
    response = post_csv(client, clients_csv.drop(columns="poutcome"))
    assert response.status_code == 422
    assert response.json()["detail"]["colonnes_manquantes"] == ["poutcome"]


def test_rank_reports_invalid_line(client, clients_csv):
    frame = clients_csv.reset_index(drop=True)
    frame.loc[3, "contact"] = "email"
    response = post_csv(client, frame)
    assert response.status_code == 422
    erreur = response.json()["detail"]["erreurs"][0]
    assert (erreur["ligne"], erreur["colonne"]) == (5, "contact")


def test_rank_rejects_empty_file(client, clients_csv):
    response = post_csv(client, clients_csv.head(0))
    assert response.status_code == 422
