from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Stage(str, Enum):
    APPLIED = "Applied"
    SCREENING = "Screening"
    INTERVIEW = "Interview"
    OFFER = "Offer"
    HIRED = "Hired"
    REJECTED = "Rejected"


ACTIVE_STAGES = [Stage.APPLIED, Stage.SCREENING, Stage.INTERVIEW, Stage.OFFER]
PIPELINE_STAGES = [*ACTIVE_STAGES, Stage.HIRED]
NEXT_STAGE = dict(zip(PIPELINE_STAGES, PIPELINE_STAGES[1:]))


class CandidateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=320)
    notes: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_name(self):
        if not self.name.strip():
            raise ValueError("Candidate name cannot be blank.")
        return self


class CandidateSummary(BaseModel):
    id: int
    name: str
    email: Optional[str]
    notes: Optional[str]
    current_stage: Stage
    current_since: datetime
    days_in_stage: float


class AuditEvent(BaseModel):
    id: int
    from_stage: Optional[Stage]
    to_stage: Stage
    event_type: str
    reason: Optional[str]
    occurred_at: datetime


class CandidateDetail(CandidateSummary):
    created_at: datetime
    history: list[AuditEvent]


class RejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    current_stage: Optional[Stage] = None
    stuck_stage: Optional[Stage] = None
    min_days_in_stage: Optional[float] = Field(default=None, ge=0)
    moved_to_stage: Optional[Stage] = None
    moved_since: Optional[datetime] = None
    reached_stage: Optional[Stage] = None
    not_hired: bool = False
    exclude_rejected: bool = False

    @model_validator(mode="after")
    def validate_filter_groups(self):
        if (self.stuck_stage is None) != (self.min_days_in_stage is None):
            raise ValueError("A time-in-stage search needs both a stage and a minimum duration.")
        if (self.moved_to_stage is None) != (self.moved_since is None):
            raise ValueError("A moved-stage search needs both a destination stage and a starting date.")
        if not any((self.name, self.current_stage, self.stuck_stage, self.moved_to_stage, self.reached_stage, self.not_hired, self.exclude_rejected)):
            raise ValueError("No candidate or pipeline filters were provided.")
        if self.current_stage and self.stuck_stage and self.current_stage != self.stuck_stage:
            raise ValueError("Current-stage and time-in-stage filters must refer to the same stage.")
        return self


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class SearchResponse(BaseModel):
    results: list[CandidateSummary]
    interpretation: Optional[SearchFilters] = None
    parser_source: str
    message: str


class SearchLog(BaseModel):
    id: int
    query: str
    parser_source: str
    interpretation: Optional[str]
    result_count: int
    message: str
    created_at: datetime
