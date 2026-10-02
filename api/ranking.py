"""Classement d'un fichier de clients par probabilité de souscription."""
import numpy as np
import pandas as pd


def rank_clients(clients: pd.DataFrame, probas: np.ndarray) -> pd.DataFrame:
    """Trie les clients par probabilité décroissante et ajoute probabilite, rang et tranche.

    Les tranches découpent le classement du fichier reçu en dix parts égales.
    """
    ranked = (
        clients.assign(probabilite=np.round(probas, 3), _proba=probas)
        .sort_values("_proba", ascending=False, kind="stable")
        .drop(columns="_proba")
        .reset_index(drop=True)
    )
    ranked["rang"] = np.arange(1, len(ranked) + 1)
    debut = (ranked.index * 10 // len(ranked)) * 10
    ranked["tranche"] = [f"{d}-{d + 10} %" for d in debut]
    return ranked
