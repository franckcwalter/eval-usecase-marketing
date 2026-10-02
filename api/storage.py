"""Conserve les prédictions et rattache les résultats de campagne aux clients."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


def connect(path: Path):
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = connect(path)
    try:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS predictions (
                client_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                features TEXT NOT NULL,
                score REAL NOT NULL,
                tranche TEXT NOT NULL,
                displayed_rate REAL NOT NULL,
                tranche_method TEXT NOT NULL,
                rank INTEGER,
                batch_id TEXT,
                model_version TEXT NOT NULL,
                request_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, campaign_id)
            );
            CREATE TABLE IF NOT EXISTS feedbacks (
                client_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                true_label INTEGER NOT NULL CHECK (true_label IN (0, 1)),
                created_at TEXT NOT NULL,
                training_run_id TEXT,
                PRIMARY KEY (client_id, campaign_id),
                FOREIGN KEY (client_id, campaign_id)
                    REFERENCES predictions (client_id, campaign_id)
            );
        """)
    finally:
        con.close()


def save_predictions(path: Path, records: list[dict]):
    con = connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            for record in records:
                record = {**record, "features": json.dumps(record["features"], sort_keys=True)}
                previous = con.execute(
                    "SELECT * FROM predictions WHERE client_id = ? AND campaign_id = ?",
                    (record["client_id"], record["campaign_id"]),
                ).fetchone()
                if previous is not None:
                    compared = ("features", "score", "tranche", "displayed_rate", "tranche_method", "rank", "model_version")
                    if any(previous[key] != record[key] for key in compared):
                        raise HTTPException(409, "Une prédiction différente existe déjà pour ce client et cette campagne")
                    continue
                record["created_at"] = datetime.now(timezone.utc).isoformat()
                keys = list(record)
                con.execute(
                    f"INSERT INTO predictions ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
                    [record[key] for key in keys],
                )
    finally:
        con.close()


def save_feedback(path: Path, client_id: str, campaign_id: str, true_label: int) -> str:
    con = connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            identifiers = (client_id, campaign_id)
            if con.execute(
                "SELECT 1 FROM predictions WHERE client_id = ? AND campaign_id = ?", identifiers,
            ).fetchone() is None:
                raise HTTPException(404, "Aucune prédiction pour ce client et cette campagne")
            previous = con.execute(
                "SELECT true_label FROM feedbacks WHERE client_id = ? AND campaign_id = ?", identifiers,
            ).fetchone()
            if previous is not None:
                if previous["true_label"] != true_label:
                    raise HTTPException(409, "Un résultat différent existe déjà : vérification nécessaire")
                return "already_stored"
            con.execute(
                "INSERT INTO feedbacks (client_id, campaign_id, true_label, created_at) VALUES (?, ?, ?, ?)",
                (*identifiers, true_label, datetime.now(timezone.utc).isoformat()),
            )
            return "stored"
    finally:
        con.close()
