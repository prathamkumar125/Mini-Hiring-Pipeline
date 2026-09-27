from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .database import connect
from .domain import ACTIVE_STAGES, NEXT_STAGE, AuditEvent, CandidateDetail, CandidateSummary, SearchFilters, SearchLog, Stage


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or now()).isoformat()


def _summary(row: sqlite3.Row) -> CandidateSummary:
    current_since = datetime.fromisoformat(row["current_since"])
    return CandidateSummary(
        id=row["id"], name=row["name"], email=row["email"], notes=row["notes"],
        current_stage=row["current_stage"], current_since=current_since,
        days_in_stage=round((now() - current_since).total_seconds() / 86400, 2),
    )


CURRENT_CANDIDATES_SQL = """
SELECT c.id, c.name, c.email, c.notes, c.created_at,
       e.to_stage AS current_stage, e.occurred_at AS current_since
FROM candidates c
JOIN candidate_events e ON e.id = (
    SELECT e2.id FROM candidate_events e2
    WHERE e2.candidate_id = c.id
    ORDER BY e2.occurred_at DESC, e2.id DESC LIMIT 1
)
"""


def create_candidate(name: str, email: str | None, notes: str | None, path: str | None = None) -> CandidateDetail:
    created = iso()
    with connect(path) as db:
        cursor = db.execute("INSERT INTO candidates(name, email, notes, created_at) VALUES (?, ?, ?, ?)", (name.strip(), email, notes, created))
        candidate_id = cursor.lastrowid
        db.execute("""INSERT INTO candidate_events(candidate_id, from_stage, to_stage, event_type, reason, occurred_at)
                      VALUES (?, NULL, ?, 'created', NULL, ?)""", (candidate_id, Stage.APPLIED.value, created))
    return get_candidate(candidate_id, path)


def list_candidates(path: str | None = None) -> list[CandidateSummary]:
    with connect(path) as db:
        rows = db.execute(CURRENT_CANDIDATES_SQL + " ORDER BY current_since ASC, name COLLATE NOCASE").fetchall()
    return [_summary(row) for row in rows]


def get_candidate(candidate_id: int, path: str | None = None) -> CandidateDetail:
    with connect(path) as db:
        row = db.execute(CURRENT_CANDIDATES_SQL + " WHERE c.id = ?", (candidate_id,)).fetchone()
        if not row:
            raise KeyError(candidate_id)
        events = db.execute("""SELECT id, from_stage, to_stage, event_type, reason, occurred_at
                               FROM candidate_events WHERE candidate_id = ? ORDER BY occurred_at, id""", (candidate_id,)).fetchall()
    summary = _summary(row)
    return CandidateDetail(**summary.model_dump(), created_at=datetime.fromisoformat(row["created_at"]), history=[AuditEvent(**dict(event)) for event in events])


def append_event(candidate_id: int, from_stage: Stage, to_stage: Stage, event_type: str, reason: str | None = None, path: str | None = None) -> CandidateDetail:
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("""SELECT to_stage FROM candidate_events WHERE candidate_id = ?
                                 ORDER BY occurred_at DESC, id DESC LIMIT 1""", (candidate_id,)).fetchone()
        if current is None:
            raise KeyError(candidate_id)
        if current["to_stage"] != from_stage.value:
            raise RuntimeError("Candidate stage changed before this transition was recorded. Refresh and try again.")
        allowed_next = NEXT_STAGE.get(from_stage)
        is_rejection = to_stage == Stage.REJECTED and from_stage in ACTIVE_STAGES
        if not is_rejection and allowed_next != to_stage:
            raise RuntimeError("Only the next pipeline stage or rejection is allowed.")
        db.execute("""INSERT INTO candidate_events(candidate_id, from_stage, to_stage, event_type, reason, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?)""", (candidate_id, from_stage.value, to_stage.value, event_type, reason, iso()))
    return get_candidate(candidate_id, path)


def query_candidates(filters: SearchFilters, path: str | None = None) -> list[CandidateSummary]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.current_stage:
        clauses.append("e.to_stage = ?")
        params.append(filters.current_stage.value)
    if filters.exclude_rejected:
        clauses.append("e.to_stage != ?")
        params.append(Stage.REJECTED.value)
    if filters.stuck_stage:
        clauses.append("e.to_stage = ?")
        params.append(filters.stuck_stage.value)
    if filters.min_days_in_stage is not None:
        clauses.append("julianday('now') - julianday(e.occurred_at) > ?")
        params.append(filters.min_days_in_stage)
    if filters.moved_to_stage and filters.moved_since:
        clauses.append("EXISTS (SELECT 1 FROM candidate_events me WHERE me.candidate_id = c.id AND me.to_stage = ? AND me.occurred_at >= ?)")
        params.extend([filters.moved_to_stage.value, iso(filters.moved_since)])
    if filters.reached_stage:
        clauses.append("EXISTS (SELECT 1 FROM candidate_events re WHERE re.candidate_id = c.id AND re.to_stage = ?)")
        params.append(filters.reached_stage.value)
    if filters.not_hired:
        clauses.append("e.to_stage != ?")
        params.append(Stage.HIRED.value)
    sql = CURRENT_CANDIDATES_SQL
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    with connect(path) as db:
        rows = db.execute(sql, params).fetchall()
    candidates = [_summary(row) for row in rows]
    if filters.name:
        from difflib import SequenceMatcher
        needle = filters.name.lower().strip()
        def score(candidate: CandidateSummary) -> float:
            name = candidate.name.lower()
            return max(SequenceMatcher(None, needle, name).ratio(), *(SequenceMatcher(None, needle, word).ratio() for word in name.split()))
        candidates = [(score(candidate), candidate) for candidate in candidates]
        candidates = [candidate for score_value, candidate in sorted(candidates, key=lambda item: (-item[0], item[1].name.lower())) if score_value >= 0.45]
    return candidates


def add_search_log(query: str, parser_source: str, interpretation: SearchFilters | None, result_count: int, message: str, path: str | None = None) -> None:
    encoded = interpretation.model_dump_json() if interpretation else None
    with connect(path) as db:
        db.execute("INSERT INTO search_logs(query, parser_source, interpretation, result_count, message, created_at) VALUES (?, ?, ?, ?, ?, ?)", (query, parser_source, encoded, result_count, message, iso()))


def list_search_logs(path: str | None = None) -> list[SearchLog]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM search_logs ORDER BY created_at DESC, id DESC").fetchall()
    return [SearchLog(**dict(row)) for row in rows]
