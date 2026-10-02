import numpy as np
import pandas as pd

from api.ranking import rank_clients


def test_tranches_follow_rank_in_file():
    clients = pd.DataFrame({"id": range(20)})
    ranked = rank_clients(clients, np.linspace(0, 1, 20))
    assert ranked["id"].iloc[0] == 19
    assert ranked["tranche"].iloc[0] == "0-10 %"
    assert ranked["tranche"].iloc[-1] == "90-100 %"
    assert ranked["tranche"].value_counts().tolist() == [2] * 10


def test_single_client_is_in_first_tranche():
    ranked = rank_clients(pd.DataFrame({"id": [1]}), np.array([0.4]))
    assert ranked[["rang", "tranche"]].iloc[0].tolist() == [1, "0-10 %"]
