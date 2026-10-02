import numpy as np
import pandas as pd

from api.ranking import rank_clients, tranche_of_score
from training.pipeline import tranche_labels

TAUX = {label: i / 10 for i, label in enumerate(tranche_labels(10))}
TRANCHES_TEST = [{"tranche": "0-10 %", "score_min": 0.8, "taux_souscription": 0.5},
                 {"tranche": "10-20 %", "score_min": 0.5, "taux_souscription": 0.2},
                 {"tranche": "20-30 %", "score_min": 0.1, "taux_souscription": 0.05}]


def test_tranches_follow_rank_in_file():
    ranked = rank_clients(pd.DataFrame({"id": range(20)}), np.linspace(0, 1, 20), TAUX)
    assert ranked["id"].iloc[0] == 19
    assert ranked["tranche"].iloc[0] == "0-10 %"
    assert ranked["tranche"].iloc[-1] == "90-100 %"
    assert ranked["tranche"].value_counts().tolist() == [2] * 10
    assert ranked["taux_reel_tranche"].iloc[-1] == 0.9


def test_single_client_is_in_first_tranche():
    ranked = rank_clients(pd.DataFrame({"id": [1]}), np.array([0.4]), TAUX)
    assert ranked[["rang", "tranche"]].iloc[0].tolist() == [1, "0-10 %"]


def test_tranche_of_score():
    assert tranche_of_score(0.9, TRANCHES_TEST)["tranche"] == "0-10 %"
    assert tranche_of_score(0.6, TRANCHES_TEST)["tranche"] == "10-20 %"
    assert tranche_of_score(0.01, TRANCHES_TEST)["tranche"] == "20-30 %"
