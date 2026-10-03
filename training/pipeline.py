"""Recette du modèle retenu au §5.6 du notebook : régression logistique, scénario S5."""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

SCENARIO = "S5"
TARGET = "y"
TARGET_MAPPING = {"no": 0, "yes": 1}
RANDOM_STATE = 42

NUMERIC_FEATURES = ["cons.conf.idx", "cons.price.idx", "emp.var.rate", "previous"]
CATEGORICAL_FEATURES = ["contact", "default", "housing", "loan", "poutcome"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

HYPERPARAMETERS = {"max_iter": 1000, "class_weight": "balanced"}


def regrouper_default(donnees):
    # default = yes ne compte que 3 clients : la modalité rejoint unknown.
    donnees = donnees.copy()
    if "default" in donnees.columns:
        donnees["default"] = donnees["default"].replace({"yes": "unknown"})
    return donnees


def tranche_labels(n: int) -> list[str]:
    """Tranche de 10 % de chaque position d'un classement de n clients, du mieux classé au moins bien classé."""
    return [f"{d}-{d + 10} %" for d in (np.arange(n) * 10 // n) * 10]


def tranches_test(y_vrai, probas) -> list[dict]:
    """Score minimal et taux réel de souscription de chaque tranche de 10 % du classement du test."""
    ordre = np.argsort(-probas, kind="stable")
    tranches = (
        pd.DataFrame({
            "tranche": tranche_labels(len(probas)),
            "score": probas[ordre],
            "souscrit": np.asarray(y_vrai)[ordre],
        })
        .groupby("tranche", sort=False)
        .agg(score_min=("score", "min"), taux_souscription=("souscrit", "mean"))
    )
    return [
        {"tranche": tranche, "score_min": round(row.score_min, 4), "taux_souscription": round(row.taux_souscription, 4)}
        for tranche, row in tranches.iterrows()
    ]


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            ("num", Pipeline([("scaler", StandardScaler())]), NUMERIC_FEATURES),
            ("cat", Pipeline([
                ("regroupement", FunctionTransformer(regrouper_default, feature_names_out="one-to-one")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return Pipeline([("prep", preprocessor), ("clf", LogisticRegression(**HYPERPARAMETERS))])
