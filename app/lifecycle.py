from __future__ import annotations

from .domain import ACTIVE_STAGES, NEXT_STAGE, CandidateDetail, Stage
from .repository import append_event, get_candidate


class TransitionError(ValueError):
    pass


def advance(candidate_id: int, path: str | None = None) -> CandidateDetail:
    candidate = get_candidate(candidate_id, path)
    current = candidate.current_stage
    if current not in NEXT_STAGE:
        raise TransitionError(f"{current.value} is a final outcome and cannot be changed.")
    try:
        return append_event(candidate_id, current, NEXT_STAGE[current], "advanced", path=path)
    except RuntimeError as exc:
        raise TransitionError(str(exc)) from exc


def reject(candidate_id: int, reason: str | None = None, path: str | None = None) -> CandidateDetail:
    candidate = get_candidate(candidate_id, path)
    if candidate.current_stage not in ACTIVE_STAGES:
        raise TransitionError(f"{candidate.current_stage.value} is a final outcome and cannot be changed.")
    try:
        return append_event(candidate_id, candidate.current_stage, Stage.REJECTED, "rejected", reason=reason or None, path=path)
    except RuntimeError as exc:
        raise TransitionError(str(exc)) from exc
