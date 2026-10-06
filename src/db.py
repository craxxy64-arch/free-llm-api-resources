import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "models.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pulls (
    id INTEGER PRIMARY KEY,
    pulled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
    pull_id INTEGER NOT NULL REFERENCES pulls(id),
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    name TEXT NOT NULL,
    limits TEXT NOT NULL,
    PRIMARY KEY (pull_id, provider, model_id)
);
CREATE INDEX IF NOT EXISTS models_provider_model ON models(provider, model_id);
"""


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def start_pull(conn):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pull_id = conn.execute("INSERT INTO pulls (pulled_at) VALUES (?)", (now,)).lastrowid
    conn.commit()
    return pull_id


def save_models(conn, pull_id, provider, models):
    conn.executemany(
        "INSERT OR REPLACE INTO models VALUES (?, ?, ?, ?, ?)",
        [
            (pull_id, provider, m["id"], m["name"], json.dumps(m.get("limits", {})))
            for m in models
        ],
    )
    conn.commit()
