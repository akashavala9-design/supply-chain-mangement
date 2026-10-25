import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
import os
DB_FILE = Path(os.getenv(
    "QUARANTINE_DB_PATH",
    "/content/quarantine_guard.db"
))


def quarantine_invalid_shipments(csv_path=None):
    csv_path = Path(csv_path) if csv_path else (
        PROJECT / "data" / "raw" / "shipments.csv"
    )

    df = pd.read_csv(csv_path)
    weight = pd.to_numeric(df["weight_tons"], errors="coerce")
    containers = pd.to_numeric(df["container_count"], errors="coerce")

    rules = {
        "Missing shipment ID":
            df["shipment_id"].isna()
            | df["shipment_id"].astype("string").str.strip().eq(""),
        "Missing or non-positive weight":
            weight.isna() | (weight <= 0),
        "Missing or non-positive container count":
            containers.isna() | (containers <= 0),
    }

    inserted = 0

    with sqlite3.connect(DB_FILE, timeout=10) as conn:
        for index, row in df.iterrows():
            reasons = [
                reason for reason, mask in rules.items()
                if bool(mask.iloc[index])
            ]

            if not reasons:
                continue

            record = row.where(pd.notna(row), None).to_dict()
            record_json = json.dumps(record, default=str)
            error_reason = "; ".join(reasons)

            exists = conn.execute(
                """
                SELECT 1 FROM quarantine
                WHERE dataset = ?
                  AND record_json = ?
                  AND error_reason = ?
                LIMIT 1
                """,
                ("shipments", record_json, error_reason),
            ).fetchone()

            if exists:
                continue

            conn.execute(
                """
                INSERT INTO quarantine
                    (dataset, record_json, error_reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "shipments",
                    record_json,
                    error_reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            inserted += 1

    return {"new_records": inserted}
