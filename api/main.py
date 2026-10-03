"""API de scoring des clients pour la campagne de dépôt à terme.

Lancement, depuis la racine du repo :
    uvicorn api.main:app --reload
"""
import csv
import io
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from loguru import logger
from pydantic import TypeAdapter, ValidationError

from api.middleware import LoggingMiddleware
from api.metrics import CAMPAIGN_RATE, DRIFT_LEVEL, OUT_OF_RANGE, REJECTIONS, MetricsMiddleware, metrics_response
from api.ranking import rank_clients, tranche_of_score
from api.schemas import CampaignCalls, Feedback, FeedbackResponse, HealthResponse, Prediction, ScoringRequest
from api.storage import (
    close_campaign, count_unused_results, initialize, read_drift, read_reports, record_calls, save_drift, save_feedback, save_predictions,
    save_report,
)
from monitoring.campaigns import evaluate_campaign, read_campaigns
from monitoring.drift import compare, outside_reference
from training.pipeline import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from training.retrain import retrain, volume_threshold

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "pipeline.joblib"
META_PATH = ROOT / "models" / "pipeline.json"
REFERENCE_PATH = ROOT / "evaluation" / "reference.csv"
FRONTEND_DIR = ROOT / "frontend"
LOGS_DIR = ROOT / "logs"
MAX_ERREURS_AFFICHEES = 20
DRIFT_LEVELS = {"insufficient_counts": -1, "no_data": -1, "stable": 0, "watch": 1, "investigate": 2}

LOGS_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(LOGS_DIR / "api.log", level="INFO", serialize=True, enqueue=True, rotation="10 MB", retention="30 days")

clients_adapter = TypeAdapter(list[ScoringRequest])


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database_path = Path(os.environ.get("FEEDBACK_DB_PATH", ROOT / "storage" / "feedback.db"))
    initialize(app.state.database_path)
    for campaign_id, report in read_reports(app.state.database_path).items():
        if report["subscription_rate"] is not None:
            CAMPAIGN_RATE.labels(campaign_id).set(report["subscription_rate"])
    for campaign_id, variables in read_drift(app.state.database_path).items():
        publish_drift(campaign_id, variables)
    app.state.model = joblib.load(MODEL_PATH)
    app.state.metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    app.state.reference = pd.read_csv(REFERENCE_PATH)
    app.state.retrain_threshold = volume_threshold()
    logger.info("Modèle chargé : {} {}", app.state.metadata["model_name"], app.state.metadata["model_version"])
    yield
    app.state.model = None


app = FastAPI(
    title="API de scoring — campagne de dépôt à terme",
    description="Score de souscription d'un client et classement d'un fichier de clients.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(MetricsMiddleware)


@app.exception_handler(RequestValidationError)
async def count_invalid_request(request: Request, exc: RequestValidationError):
    REJECTIONS.labels(request.url.path, "valeur_invalide").inc()
    return await request_validation_exception_handler(request, exc)


def reject(route: str, motif: str, detail):
    REJECTIONS.labels(route, motif).inc()
    return HTTPException(status_code=422, detail=detail)


def predict_scores(features: pd.DataFrame):
    try:
        return app.state.model.predict_proba(features[FEATURES])[:, 1]
    except Exception as exc:
        logger.exception("Échec de la prédiction")
        raise HTTPException(status_code=500, detail="Échec de la prédiction") from exc


def read_csv(content: bytes, route: str) -> tuple[pd.DataFrame, str]:
    try:
        text = content.decode("utf-8-sig")
        sep = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;").delimiter
        return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False), sep
    except (UnicodeDecodeError, IndexError, csv.Error, pd.errors.ParserError) as exc:
        raise reject(route, "fichier_illisible", "Fichier illisible : CSV encodé en UTF-8 attendu") from exc


def parse_clients(content: bytes, route: str) -> tuple[pd.DataFrame, str, pd.DataFrame]:
    clients, sep = read_csv(content, route)
    if clients.empty:
        raise reject(route, "fichier_vide", "Le fichier ne contient aucun client")

    manquantes = [col for col in [*FEATURES, "client_id", "campaign_id"] if col not in clients.columns]
    if manquantes:
        raise reject(route, "colonnes_manquantes", {"colonnes_manquantes": manquantes})

    try:
        profils = clients_adapter.validate_python(clients[[*FEATURES, "client_id", "campaign_id"]].to_dict("records"))
    except ValidationError as exc:
        erreurs = [
            {"ligne": err["loc"][0] + 2, "colonne": err["loc"][1], "message": err["msg"]}
            for err in exc.errors()[:MAX_ERREURS_AFFICHEES]
        ]
        raise reject(route, "valeur_invalide", {"nb_erreurs": exc.error_count(), "erreurs": erreurs}) from exc

    validated = pd.DataFrame([profil.model_dump(by_alias=True) for profil in profils])
    if validated.duplicated(["client_id", "campaign_id"]).any():
        raise reject(route, "client_en_double", "Un client apparaît plusieurs fois dans la même campagne")
    if validated["campaign_id"].nunique() != 1:
        raise reject(route, "plusieurs_campagnes", "Le fichier doit contenir une seule campagne")
    clients[["client_id", "campaign_id"]] = validated[["client_id", "campaign_id"]]
    return clients, sep, validated


def measure_drift(validated: pd.DataFrame) -> list[dict]:
    return compare(app.state.reference, validated[FEATURES], NUMERIC_FEATURES, CATEGORICAL_FEATURES)


def publish_drift(campaign_id: str, variables: list[dict]):
    for row in variables:
        DRIFT_LEVEL.labels(campaign_id, row["feature"]).set(DRIFT_LEVELS[row["status"]])


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if getattr(app.state, "model", None) is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return HealthResponse(status="ok", model_version=app.state.metadata["model_version"])


@app.post("/predict", response_model=Prediction)
def predict(client: ScoringRequest, request: Request) -> Prediction:
    entrees = client.model_dump(by_alias=True, exclude={"client_id", "campaign_id"})
    score = round(float(predict_scores(pd.DataFrame([entrees]))[0]), 3)
    tranche = tranche_of_score(score, app.state.metadata["tranches_test"])
    hors_historique = bool(outside_reference(app.state.reference, pd.DataFrame([entrees]), NUMERIC_FEATURES).iloc[0])
    if hors_historique:
        OUT_OF_RANGE.labels("/predict").inc()
    save_predictions(app.state.database_path, [{
        "client_id": client.client_id, "campaign_id": client.campaign_id,
        "features": entrees, "score": score, "tranche": tranche["tranche"],
        "displayed_rate": tranche["taux_souscription"], "tranche_method": "test_score_bounds",
        "rank": None, "batch_id": None, "model_version": app.state.metadata["model_version"],
        "request_id": request.state.request_id,
    }])
    logger.bind(
        request_id=request.state.request_id, entrees=entrees, score=score, tranche=tranche["tranche"]
    ).info("Prédiction")
    return Prediction(
        score=score,
        tranche=tranche["tranche"],
        taux_reel_tranche=tranche["taux_souscription"],
        model_version=app.state.metadata["model_version"],
        request_id=request.state.request_id,
        hors_historique=hors_historique,
    )


@app.post(
    "/rank",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV des clients classés"}},
)
def rank(file: UploadFile, request: Request) -> Response:
    """Classe les clients d'un CSV par score décroissant.

    Le CSV renvoyé reprend toutes les colonnes reçues et ajoute score, rang, tranche et taux_reel_tranche.
    """
    clients, sep, validated = parse_clients(file.file.read(), "/rank")
    features = validated[FEATURES]
    taux_par_tranche = {t["tranche"]: t["taux_souscription"] for t in app.state.metadata["tranches_test"]}
    outside = outside_reference(app.state.reference, validated, NUMERIC_FEATURES)
    OUT_OF_RANGE.labels("/rank").inc(int(outside.sum()))
    clients["hors_historique"] = outside.map({True: "oui", False: "non"}).to_numpy()
    ranked = rank_clients(clients, predict_scores(features), taux_par_tranche)
    features_by_client = dict(zip(validated["client_id"], features.to_dict("records")))
    save_predictions(app.state.database_path, [{
        "client_id": row["client_id"], "campaign_id": row["campaign_id"],
        "features": features_by_client[row["client_id"]], "score": row["score"],
        "tranche": row["tranche"], "displayed_rate": row["taux_reel_tranche"],
        "tranche_method": "batch_rank", "rank": row["rang"],
        "batch_id": request.state.request_id, "model_version": app.state.metadata["model_version"],
        "request_id": request.state.request_id,
    } for row in ranked.to_dict("records")])
    campaign_id = validated["campaign_id"].iloc[0]
    variables = measure_drift(validated)
    save_drift(app.state.database_path, campaign_id, variables)
    publish_drift(campaign_id, variables)
    logger.bind(
        request_id=request.state.request_id,
        fichier=file.filename,
        nb_clients=len(ranked),
        score_moyen=round(float(ranked["score"].mean()), 3),
    ).info("Classement")

    return Response(
        content=ranked.to_csv(sep=sep, index=False),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="clients_classes.csv"'},
    )


@app.post("/drift")
def drift(file: UploadFile) -> dict:
    """Compare les profils d'un fichier de clients à ceux du test historique."""
    _, _, validated = parse_clients(file.file.read(), "/drift")
    outside = outside_reference(app.state.reference, validated, NUMERIC_FEATURES)
    return {"campaign_id": validated["campaign_id"].iloc[0], "n_clients": len(validated),
            "n_reference": len(app.state.reference), "variables": measure_drift(validated),
            "outside_clients": validated.loc[outside, "client_id"].tolist()}


@app.post("/feedback", response_model=FeedbackResponse, status_code=201)
def feedback(result: Feedback) -> FeedbackResponse:
    status = save_feedback(app.state.database_path, result.client_id, result.campaign_id, result.true_label)
    return FeedbackResponse(status=status, client_id=result.client_id, campaign_id=result.campaign_id)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.post("/campaigns/{campaign_id}/calls")
def campaign_calls(campaign_id: str, body: CampaignCalls):
    count = record_calls(app.state.database_path, campaign_id, body.client_ids, body.selected_top50)
    return {"campaign_id": campaign_id, "called": count}


@app.post("/campaigns/{campaign_id}/close")
def campaign_close(campaign_id: str):
    close_campaign(app.state.database_path, campaign_id)
    campaigns = read_campaigns(app.state.database_path)
    report = evaluate_campaign(campaigns.loc[campaigns.campaign_id == campaign_id])
    save_report(app.state.database_path, campaign_id, report)
    if report["subscription_rate"] is not None:
        CAMPAIGN_RATE.labels(campaign_id).set(report["subscription_rate"])
    rate = report["subscription_rate"]
    below_threshold = rate is not None and rate < report["threshold"]
    unused = count_unused_results(app.state.database_path)
    triggers = [name for name, met in (("volume", unused >= app.state.retrain_threshold), ("degradation", below_threshold)) if met]
    retraining = retrain(app.state.database_path, "+".join(triggers)) if triggers else None
    return {"campaign_id": campaign_id, "status": "closed", "subscription_rate": rate,
            "subscriptions": report["subscriptions"], "selected_known": report["selected_known"],
            "selected_expected": report["selected_expected"],
            "confidence_interval_95": report["confidence_interval_95"], "threshold": report["threshold"],
            "below_threshold": below_threshold,
            "tranches": [row for row in report["tranches"] if row["method"] == "batch_rank"],
            "unused_results": unused, "retrain_threshold": app.state.retrain_threshold, "retraining": retraining}


app.frontend("/", directory=FRONTEND_DIR)
