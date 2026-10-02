"""API de scoring des clients pour la campagne de dépôt à terme.

Lancement, depuis la racine du repo :
    uvicorn api.main:app --reload
"""
import csv
import io
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from loguru import logger
from pydantic import TypeAdapter, ValidationError

from api.middleware import LoggingMiddleware
from api.ranking import rank_clients
from api.schemas import ClientProfile, HealthResponse, Prediction
from training.pipeline import FEATURES

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "pipeline.joblib"
META_PATH = ROOT / "models" / "pipeline.json"
LOGS_DIR = ROOT / "logs"
MAX_ERREURS_AFFICHEES = 20

LOGS_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(LOGS_DIR / "api.log", level="INFO", serialize=True, enqueue=True, rotation="10 MB", retention="30 days")

clients_adapter = TypeAdapter(list[ClientProfile])


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = joblib.load(MODEL_PATH)
    app.state.metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    logger.info("Modèle chargé : {} {}", app.state.metadata["model_name"], app.state.metadata["model_version"])
    yield
    app.state.model = None


app = FastAPI(
    title="API de scoring — campagne de dépôt à terme",
    description="Probabilité de souscription d'un client et classement d'un fichier de clients.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)


def predict_probas(features: pd.DataFrame):
    try:
        return app.state.model.predict_proba(features[FEATURES])[:, 1]
    except Exception as exc:
        logger.exception("Échec de la prédiction")
        raise HTTPException(status_code=500, detail="Échec de la prédiction") from exc


def read_csv(content: bytes) -> tuple[pd.DataFrame, str]:
    try:
        text = content.decode("utf-8-sig")
        sep = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;").delimiter
        return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False), sep
    except (UnicodeDecodeError, IndexError, csv.Error, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail="Fichier illisible : CSV encodé en UTF-8 attendu") from exc


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if getattr(app.state, "model", None) is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return HealthResponse(status="ok", model_version=app.state.metadata["model_version"])


@app.post("/predict", response_model=Prediction)
def predict(client: ClientProfile, request: Request) -> Prediction:
    entrees = client.model_dump(by_alias=True)
    probabilite = round(float(predict_probas(pd.DataFrame([entrees]))[0]), 3)
    logger.bind(request_id=request.state.request_id, entrees=entrees, probabilite=probabilite).info("Prédiction")
    return Prediction(
        probabilite=probabilite,
        model_version=app.state.metadata["model_version"],
        request_id=request.state.request_id,
    )


@app.post(
    "/rank",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV des clients classés"}},
)
def rank(file: UploadFile, request: Request) -> Response:
    """Classe les clients d'un CSV par probabilité de souscription décroissante.

    Le CSV renvoyé reprend toutes les colonnes reçues et ajoute probabilite, rang et tranche.
    """
    clients, sep = read_csv(file.file.read())
    if clients.empty:
        raise HTTPException(status_code=422, detail="Le fichier ne contient aucun client")

    manquantes = [col for col in FEATURES if col not in clients.columns]
    if manquantes:
        raise HTTPException(status_code=422, detail={"colonnes_manquantes": manquantes})

    try:
        profils = clients_adapter.validate_python(clients[FEATURES].to_dict("records"))
    except ValidationError as exc:
        erreurs = [
            {"ligne": err["loc"][0] + 2, "colonne": err["loc"][1], "message": err["msg"]}
            for err in exc.errors()[:MAX_ERREURS_AFFICHEES]
        ]
        raise HTTPException(status_code=422, detail={"nb_erreurs": exc.error_count(), "erreurs": erreurs}) from exc

    features = pd.DataFrame([profil.model_dump(by_alias=True) for profil in profils])
    ranked = rank_clients(clients, predict_probas(features))
    logger.bind(
        request_id=request.state.request_id,
        fichier=file.filename,
        nb_clients=len(ranked),
        probabilite_moyenne=round(float(ranked["probabilite"].mean()), 3),
    ).info("Classement")

    return Response(
        content=ranked.to_csv(sep=sep, index=False),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="clients_classes.csv"'},
    )
