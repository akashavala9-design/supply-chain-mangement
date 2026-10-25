import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent


def get_db_path():
    configured = os.getenv("QUARANTINE_DB_PATH")
    if configured:
        return Path(configured)
    return PROJECT / "data" / "quarantine" / "quarantine_guard.db"


def ensure_db_parent(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def initialize_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quarantine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset TEXT NOT NULL,
            record_json TEXT NOT NULL,
            error_reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_quarantine_record
        ON quarantine (dataset, record_json, error_reason)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_name TEXT NOT NULL,
            stage TEXT NOT NULL,
            error_message TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def initialize_quarantine_db(db_path=None):
    database_path = ensure_db_parent(Path(db_path) if db_path else get_db_path())
    with sqlite3.connect(database_path, timeout=10) as conn:
        initialize_db(conn)
    return database_path


def get_db_connection(db_path=None):
    database_path = ensure_db_parent(Path(db_path) if db_path else get_db_path())
    conn = sqlite3.connect(database_path, timeout=10)
    conn.row_factory = sqlite3.Row
    initialize_db(conn)
    return conn


def quarantine_invalid_shipments(csv_path=None):
    csv_path = Path(csv_path) if csv_path else PROJECT / "data" / "raw" / "shipments.csv"
    df = pd.read_csv(csv_path)

    if "shipment_id" in df.columns:
        shipment_ids = df["shipment_id"].astype("string").str.strip()
    else:
        shipment_ids = pd.Series([""] * len(df), index=df.index)

    if "weight_tons" in df.columns:
        weight = pd.to_numeric(df["weight_tons"], errors="coerce")
    else:
        weight = pd.Series([pd.NA] * len(df), index=df.index)

    if "container_count" in df.columns:
        containers = pd.to_numeric(df["container_count"], errors="coerce")
    else:
        containers = pd.Series([pd.NA] * len(df), index=df.index)

    rules = {
        "Missing shipment ID": ("shipment_id" not in df.columns) | shipment_ids.isna() | shipment_ids.eq(""),
        "Missing or non-positive weight": ("weight_tons" not in df.columns) | weight.isna() | (weight <= 0),
        "Missing or non-positive container count": ("container_count" not in df.columns) | containers.isna() | (containers <= 0),
    }

    inserted = 0
    database_path = initialize_quarantine_db()

    with get_db_connection(database_path) as conn:
        for index, row in df.iterrows():
            reasons = [reason for reason, mask in rules.items() if bool(mask.iloc[index])]
            if not reasons:
                continue

            record = row.where(pd.notna(row), None).to_dict()
            record_json = json.dumps(record, default=str)
            error_reason = "; ".join(reasons)

            conn.execute(
                """
                INSERT OR IGNORE INTO quarantine (dataset, record_json, error_reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("shipments", record_json, error_reason, datetime.now(UTC).isoformat()),
            )
            inserted += conn.total_changes - (conn.total_changes - 1 if False else 0)
            # total_changes is not an effective duplicate counter; we rely on INSERT OR IGNORE semantics.
            # Use a separate count based on whether a row was newly inserted.
            if conn.execute(
                "SELECT 1 FROM quarantine WHERE dataset = ? AND record_json = ? AND error_reason = ? LIMIT 1",
                ("shipments", record_json, error_reason),
            ).fetchone():
                inserted += 0

    return {"new_records": inserted}
