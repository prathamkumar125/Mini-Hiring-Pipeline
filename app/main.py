from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .database import get_db_path, initialize_database
from .domain import CandidateCreate, CandidateDetail, CandidateSummary, RejectRequest, SearchLog, SearchRequest, SearchResponse
from .lifecycle import TransitionError, advance, reject
from .repository import add_search_log, create_candidate, get_candidate, list_candidates, list_search_logs, query_candidates
from .search import SearchParseError, interpret_query


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(get_db_path())
    yield


app = FastAPI(title="Mini Hiring Pipeline", version="1.0.0", lifespan=lifespan)


@app.post("/candidates", response_model=CandidateDetail, status_code=201)
def add_candidate(payload: CandidateCreate):
    return create_candidate(payload.name, payload.email, payload.notes)


@app.get("/candidates", response_model=list[CandidateSummary])
def candidates():
    return list_candidates()


@app.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def candidate(candidate_id: int):
    try: return get_candidate(candidate_id)
    except KeyError: raise HTTPException(404, "Candidate not found")


@app.post("/candidates/{candidate_id}/advance", response_model=CandidateDetail)
def advance_candidate(candidate_id: int):
    try: return advance(candidate_id)
    except KeyError: raise HTTPException(404, "Candidate not found")
    except TransitionError as exc: raise HTTPException(409, str(exc))


@app.post("/candidates/{candidate_id}/reject", response_model=CandidateDetail)
def reject_candidate(candidate_id: int, payload: RejectRequest):
    try: return reject(candidate_id, payload.reason)
    except KeyError: raise HTTPException(404, "Candidate not found")
    except TransitionError as exc: raise HTTPException(409, str(exc))


@app.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest):
    try:
        filters, source, message = interpret_query(payload.query)
        results = query_candidates(filters)
        response = SearchResponse(results=results, interpretation=filters, parser_source=source, message=message)
    except SearchParseError as exc:
        response = SearchResponse(results=[], interpretation=None, parser_source="error", message=str(exc))
    add_search_log(payload.query, response.parser_source, response.interpretation, len(response.results), response.message)
    return response


@app.get("/search/logs", response_model=list[SearchLog])
def search_logs():
    return list_search_logs()
