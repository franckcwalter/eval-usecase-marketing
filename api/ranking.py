"""Classement des clients et lecture des tranches de 10 % mesurées sur le jeu de test."""
import numpy as np
import pandas as pd

from training.pipeline import tranche_labels


def rank_clients(clients: pd.DataFrame, scores: np.ndarray, taux_par_tranche: dict[str, float]) -> pd.DataFrame:
    """Trie les clients par score décroissant et ajoute score, rang, tranche et taux_reel_tranche.

    Les tranches découpent le classement du fichier reçu en dix parts égales.
    """
    ranked = (
        clients.assign(score=np.round(scores, 3), _score=scores)
        .sort_values("_score", ascending=False, kind="stable")
        .drop(columns="_score")
        .reset_index(drop=True)
    )
    ranked["rang"] = np.arange(1, len(ranked) + 1)
    ranked["tranche"] = tranche_labels(len(ranked))
    ranked["taux_reel_tranche"] = ranked["tranche"].map(taux_par_tranche)
    return ranked


def tranche_of_score(score: float, tranches_test: list[dict]) -> dict:
    """Tranche du test dans laquelle tombe un score : la première dont le score minimal est atteint."""
    return next((t for t in tranches_test if score >= t["score_min"]), tranches_test[-1])
