from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.domain import SearchFilters, Stage
from app.lifecycle import TransitionError, advance, reject
from app.repository import append_event, create_candidate, get_candidate, query_candidates
from app.search import SearchParseError, parse_fallback


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    initialize_database(path)
    return path


def test_lifecycle_and_terminal_protection(db_path):
    candidate = create_candidate("Priya Sharma", None, None, db_path)
    candidate = advance(candidate.id, db_path)
    assert candidate.current_stage == Stage.SCREENING
    candidate = reject(candidate.id, "Not a fit", db_path)
    assert candidate.current_stage == Stage.REJECTED
    assert candidate.history[-1].reason == "Not a fit"
    with pytest.raises(TransitionError): advance(candidate.id, db_path)


def test_audit_events_cannot_change_or_delete(db_path):
    candidate = create_candidate("Asha Rao", None, None, db_path)
    with sqlite3.connect(db_path) as db:
        with pytest.raises(sqlite3.DatabaseError): db.execute("DELETE FROM candidate_events WHERE candidate_id = ?", (candidate.id,))
        with pytest.raises(sqlite3.DatabaseError): db.execute("UPDATE candidate_events SET reason = 'changed' WHERE candidate_id = ?", (candidate.id,))


def test_fuzzy_and_combined_search(db_path):
    priya = create_candidate("Priya Sharma", None, None, db_path)
    advance(priya.id, db_path); advance(priya.id, db_path)
    other = create_candidate("Mina Das", None, None, db_path)
    reject(other.id, path=db_path)
    assert [item.name for item in query_candidates(SearchFilters(name="sharam"), db_path)] == ["Priya Sharma"]
    results = query_candidates(SearchFilters(current_stage=Stage.INTERVIEW, exclude_rejected=True), db_path)
    assert [item.name for item in results] == ["Priya Sharma"]


def test_fallback_examples_and_invalid_query():
    assert parse_fallback("MLE").name == "mle"
    assert parse_fallback("Who's in Interview right now?").current_stage == Stage.INTERVIEW
    stuck = parse_fallback("stuck in Screening for more than a week")
    assert stuck.stuck_stage == Stage.SCREENING and stuck.min_days_in_stage == 7
    assert parse_fallback("Who reached the Offer stage but didn't get hired?").reached_stage == Stage.OFFER
    with pytest.raises(SearchParseError): parse_fallback("calculate average salary by geography")


def test_api_round_trip(tmp_path, monkeypatch):
    db_path = str(tmp_path / "api.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    from app.main import app
    with TestClient(app) as client:
        created = client.post("/candidates", json={"name": "Priya Sharma"})
        assert created.status_code == 201
        candidate_id = created.json()["id"]
        assert client.post(f"/candidates/{candidate_id}/advance").status_code == 200
        result = client.post("/search", json={"query": "sharam"})
        assert result.status_code == 200
        assert result.json()["results"][0]["name"] == "Priya Sharma"
        assert client.get("/search/logs").json()[0]["query"] == "sharam"
