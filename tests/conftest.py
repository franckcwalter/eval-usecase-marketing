from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "bank-additional-full.csv"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDBACK_DB_PATH", str(tmp_path / "feedback.db"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_payload() -> dict:
    return {
        "client_id": "000123",
        "campaign_id": "campagne-2026-10",
        "contact": "cellular",
        "default": "no",
        "housing": "yes",
        "loan": "no",
        "poutcome": "nonexistent",
        "previous": 0,
        "emp.var.rate": -1.8,
        "cons.price.idx": 92.893,
        "cons.conf.idx": -46.2,
    }


@pytest.fixture
def clients_csv() -> pd.DataFrame:
    frame = pd.read_csv(DATA_PATH, sep=";").drop(columns="y").sample(50, random_state=0)
    frame["client_id"] = [f"{i:06d}" for i in range(len(frame))]
    frame["campaign_id"] = "campagne-2026-10"
    return frame
