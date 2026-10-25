import sqlite3

from app.main import initialize_incidents_db
from app.quarantine import initialize_quarantine_db


def test_initialize_quarantine_db_creates_missing_parent_and_table(tmp_path):
    db_path = tmp_path / "nested" / "db" / "quarantine_guard.db"

    result = initialize_quarantine_db(db_path)

    assert result == db_path
    assert db_path.parent.exists()
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='quarantine'"
        ).fetchall()
    assert tables == [("quarantine",)]


def test_initialize_quarantine_db_is_idempotent(tmp_path):
    db_path = tmp_path / "quarantine_guard.db"

    initialize_quarantine_db(db_path)
    initialize_quarantine_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='quarantine'"
        ).fetchall()
    assert tables == [("quarantine",)]


def test_initialize_incidents_db_creates_missing_table(tmp_path):
    db_path = tmp_path / "incidents.db"

    result = initialize_incidents_db(db_path)

    assert result == db_path
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'"
        ).fetchall()
    assert tables == [("incidents",)]


def test_initialize_incidents_db_is_idempotent(tmp_path):
    db_path = tmp_path / "incidents.db"

    initialize_incidents_db(db_path)
    initialize_incidents_db(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'"
        ).fetchall()
    assert tables == [("incidents",)]
