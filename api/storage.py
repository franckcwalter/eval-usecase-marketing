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
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                closed INTEGER NOT NULL DEFAULT 0,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS campaign_calls (
                client_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, campaign_id),
                FOREIGN KEY (client_id, campaign_id)
                    REFERENCES predictions (client_id, campaign_id)
            );
            CREATE TABLE IF NOT EXISTS campaign_reports (
                campaign_id TEXT PRIMARY KEY REFERENCES campaigns (campaign_id),
                report TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS retrainings (
                run_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS campaign_drift (
                campaign_id TEXT PRIMARY KEY,
                variables TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO campaign_calls (client_id, campaign_id, created_at)
                SELECT client_id, campaign_id, created_at FROM feedbacks;
        """)
    finally:
        con.close()


def save_predictions(path: Path, records: list[dict]):
    con = connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            for record in records:
                state = con.execute("SELECT closed FROM campaigns WHERE campaign_id = ?", (record["campaign_id"],)).fetchone()
                if state and state["closed"]:
                    raise HTTPException(409, "Cette campagne est clôturée")
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
            state = con.execute("SELECT closed FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            if state and state["closed"]:
                raise HTTPException(409, "Cette campagne est clôturée")
            con.execute(
                "INSERT OR IGNORE INTO campaign_calls VALUES (?, ?, ?)",
                (*identifiers, datetime.now(timezone.utc).isoformat()),
            )
            con.execute(
                "INSERT INTO feedbacks (client_id, campaign_id, true_label, created_at) VALUES (?, ?, ?, ?)",
                (*identifiers, true_label, datetime.now(timezone.utc).isoformat()),
            )
            return "stored"
    finally:
        con.close()


def record_calls(path: Path, campaign_id: str, client_ids: list[str], selected: bool = False):
    con = connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            predictions = con.execute("SELECT client_id, tranche_method, tranche FROM predictions WHERE campaign_id = ?", (campaign_id,)).fetchall()
            if not predictions:
                raise HTTPException(404, "Campagne inconnue")
            state = con.execute("SELECT closed FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
            if state and state["closed"]:
                raise HTTPException(409, "Cette campagne est clôturée")
            if selected:
                client_ids = [r["client_id"] for r in predictions if r["tranche_method"] == "batch_rank" and int(r["tranche"].split("-")[0]) < 50]
            if not client_ids or not set(client_ids) <= {r["client_id"] for r in predictions}:
                raise HTTPException(422, "Indiquer des clients classés dans cette campagne")
            now = datetime.now(timezone.utc).isoformat()
            con.executemany("INSERT OR IGNORE INTO campaign_calls VALUES (?, ?, ?)", [(cid, campaign_id, now) for cid in client_ids])
            con.execute("INSERT OR IGNORE INTO campaigns (campaign_id) VALUES (?)", (campaign_id,))
            return con.execute("SELECT COUNT(*) FROM campaign_calls WHERE campaign_id = ?", (campaign_id,)).fetchone()[0]
    finally:
        con.close()


def close_campaign(path: Path, campaign_id: str):
    con = connect(path)
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM feedbacks WHERE campaign_id = ?", (campaign_id,)).fetchone():
                raise HTTPException(422, "Renseigner au moins un résultat avant de terminer la campagne")
            con.execute("""INSERT INTO campaigns VALUES (?, 1, ?)
                ON CONFLICT (campaign_id) DO UPDATE SET closed = 1, closed_at = COALESCE(closed_at, excluded.closed_at)
            """, (campaign_id, datetime.now(timezone.utc).isoformat()))
    finally:
        con.close()


def save_report(path: Path, campaign_id: str, report: dict):
    con = connect(path)
    try:
        with con:
            con.execute(
                "INSERT OR REPLACE INTO campaign_reports VALUES (?, ?, ?)",
                (campaign_id, json.dumps(report, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )
    finally:
        con.close()


def read_reports(path: Path) -> dict[str, dict]:
    con = connect(path)
    try:
        return {row["campaign_id"]: json.loads(row["report"]) for row in con.execute("SELECT * FROM campaign_reports")}
    finally:
        con.close()


def save_drift(path: Path, campaign_id: str, variables: list[dict]):
    con = connect(path)
    try:
        with con:
            con.execute(
                "INSERT OR REPLACE INTO campaign_drift VALUES (?, ?, ?)",
                (campaign_id, json.dumps(variables), datetime.now(timezone.utc).isoformat()),
            )
    finally:
        con.close()


def read_drift(path: Path) -> dict[str, list[dict]]:
    con = connect(path)
    try:
        return {row["campaign_id"]: json.loads(row["variables"]) for row in con.execute("SELECT * FROM campaign_drift")}
    finally:
        con.close()


def count_unused_results(path: Path) -> int:
    con = connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM feedbacks WHERE training_run_id IS NULL").fetchone()[0]
    finally:
        con.close()
