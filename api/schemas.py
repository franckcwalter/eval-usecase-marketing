"""Schémas d'entrée et de sortie de l'API.

Les alias reprennent les noms de colonnes du fichier de données, qui contiennent des points.
"""
from typing import Literal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

YesNoUnknown = Literal["no", "unknown", "yes"]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ClientProfile(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [{
                "contact": "cellular",
                "default": "no",
                "housing": "yes",
                "loan": "no",
                "poutcome": "nonexistent",
                "previous": 0,
                "emp.var.rate": -1.8,
                "cons.price.idx": 92.893,
                "cons.conf.idx": -46.2,
            }]
        },
    )

    contact: Literal["cellular", "telephone"] = Field(description="Canal du dernier contact")
    default: YesNoUnknown = Field(description="Défaut de crédit connu")
    housing: YesNoUnknown = Field(description="Prêt immobilier en cours")
    loan: YesNoUnknown = Field(description="Prêt personnel en cours")
    poutcome: Literal["failure", "nonexistent", "success"] = Field(
        description="Résultat de la campagne précédente"
    )
    previous: int = Field(ge=0, description="Nombre de contacts avant cette campagne")
    emp_var_rate: float = Field(alias="emp.var.rate", description="Taux de variation de l'emploi, trimestriel")
    cons_price_idx: float = Field(alias="cons.price.idx", gt=0, description="Indice des prix à la consommation, mensuel")
    cons_conf_idx: float = Field(alias="cons.conf.idx", description="Indice de confiance des consommateurs, mensuel")


class Prediction(BaseModel):
    score: float = Field(ge=0.0, le=1.0, description="Score du modèle, sert à classer les clients entre eux")
    tranche: str = Field(description="Tranche de 10 % du classement du jeu de test où tombe ce score")
    taux_reel_tranche: float = Field(description="Taux de souscription mesuré dans cette tranche sur le jeu de test")
    model_version: str
    request_id: str


class ScoringRequest(ClientProfile):
    client_id: Identifier
    campaign_id: Identifier


class Feedback(BaseModel):
    client_id: Identifier
    campaign_id: Identifier
    true_label: int = Field(strict=True, ge=0, le=1)


class FeedbackResponse(BaseModel):
    status: Literal["stored", "already_stored"]
    client_id: str
    campaign_id: str


class CampaignCalls(BaseModel):
    client_ids: list[Identifier] = Field(default_factory=list, max_length=100000)
    selected_top50: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_version: str
