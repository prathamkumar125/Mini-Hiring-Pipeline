from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import DATABASE_PATH


def get_db_path() -> str:
    # Read at call time so test suites can override DATABASE_PATH safely.
    import os
    return os.getenv("DATABASE_PATH", DATABASE_PATH)


def connect(path: str | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(path or get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: str | None = None) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL REFERENCES candidates(id),
                from_stage TEXT,
                to_stage TEXT NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT,
                occurred_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_candidate_time
                ON candidate_events(candidate_id, occurred_at, id);
            CREATE INDEX IF NOT EXISTS idx_events_stage_time
                ON candidate_events(to_stage, occurred_at);

            CREATE TABLE IF NOT EXISTS search_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                parser_source TEXT NOT NULL,
                interpretation TEXT,
                result_count INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS prevent_event_update
            BEFORE UPDATE ON candidate_events
            BEGIN SELECT RAISE(ABORT, 'candidate events are immutable'); END;

            CREATE TRIGGER IF NOT EXISTS prevent_event_delete
            BEFORE DELETE ON candidate_events
            BEGIN SELECT RAISE(ABORT, 'candidate events are immutable'); END;
            """
        )
