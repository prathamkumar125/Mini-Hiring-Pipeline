from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from .config import OLLAMA_MODEL
from .domain import SearchFilters, Stage


class SearchParseError(ValueError):
    pass


STAGE_BY_TEXT = {stage.value.lower(): stage for stage in Stage}


def _monday() -> datetime:
    current = datetime.now(timezone.utc)
    return (current - timedelta(days=current.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_fallback(query: str) -> SearchFilters:
    text = " ".join(query.lower().strip().split())
    if not text:
        raise SearchParseError("Enter a candidate name or a supported pipeline question.")
    # Build provisionally, then validate the complete filter set after parsing.
    filters = SearchFilters.model_construct()
    recognized = False
    if "except rejected" in text or "excluding rejected" in text:
        filters.exclude_rejected = True; recognized = True
    if re.search(r"reached (the )?offer.*(didn't|did not|not) get hired", text):
        filters.reached_stage = Stage.OFFER; filters.not_hired = True; recognized = True
    moved = re.search(r"moved to (applied|screening|interview|offer|hired) since monday", text)
    if moved:
        filters.moved_to_stage = STAGE_BY_TEXT[moved.group(1)]; filters.moved_since = _monday(); recognized = True
    stuck = re.search(r"stuck in (applied|screening|interview|offer) for more than (?:a |an )?(\d+)?\s*(day|days|week|weeks)", text)
    if stuck:
        amount = int(stuck.group(2) or 1); days = amount * (7 if "week" in stuck.group(3) else 1)
        filters.stuck_stage = STAGE_BY_TEXT[stuck.group(1)]; filters.min_days_in_stage = days; recognized = True
    current = re.search(r"(?:who'?s|who is|in) (applied|screening|interview|offer|hired|rejected)(?: right now| currently)?", text)
    if current:
        filters.current_stage = STAGE_BY_TEXT[current.group(1)]; recognized = True
    name_match = re.match(r"find (.+?)(?:\s+and\s+.+)?$", text)
    if name_match:
        filters.name = name_match.group(1).strip(); recognized = True
    elif recognized and " and " in text:
        query_terms = {"who", "in", "stuck", "moved", "reached", "except", "excluding", "everyone", "applied", "screening", "interview", "offer", "hired", "rejected"}
        for clause in text.split(" and "):
            possible_name = clause.strip()
            if possible_name.startswith(("who's ", "who is ")):
                possible_name = re.sub(r"^who(?:'s| is)\s+", "", possible_name)
            if re.fullmatch(r"[a-z .'-]{2,80}", possible_name) and not (set(possible_name.split()) & query_terms):
                filters.name = possible_name
                break
    elif recognized:
        residual = text
        residual = re.sub(r"(?:who'?s|who is)?\s*(?:in\s+)(?:applied|screening|interview|offer|hired|rejected)(?:\s+right now|\s+currently)?", " ", residual)
        residual = re.sub(r"(?:who has been |who'?s been )?stuck in (?:applied|screening|interview|offer) for more than (?:a |an )?(?:\d+\s*)?(?:day|days|week|weeks)", " ", residual)
        residual = re.sub(r"(?:who )?moved to (?:applied|screening|interview|offer|hired) since monday", " ", residual)
        residual = re.sub(r"(?:who )?reached (?:the )?offer(?: stage)? but (?:didn't|did not|not) get hired", " ", residual)
        residual = residual.replace("everyone", " ").replace("candidates", " ")
        residual = re.sub(r"\b(?:and|who|has|have|been|the|except|excluding|not|get|hired|but|right|now|currently|applied|screening|interview|offer|rejected)\b", " ", residual)
        residual = re.sub(r"[^a-z .'-]", " ", residual)
        residual = " ".join(residual.split()).strip(" .-'\t")
        if residual and re.fullmatch(r"[a-z .'-]{2,80}", residual):
            filters.name = residual
    elif not recognized and re.fullmatch(r"[a-z .'-]{2,80}", text):
        unsupported = {"calculate", "average", "salary", "geography", "delete", "update", "sql"}
        if not (set(re.findall(r"[a-z]+", text)) & unsupported):
            filters.name = text; recognized = True
    if not recognized:
        raise SearchParseError("I couldn't interpret that. Try a name, 'in Interview', 'stuck in Screening for more than a week', or combine supported phrases with 'and'.")
    return SearchFilters.model_validate(filters.model_dump())


def parse_with_ollama(query: str) -> SearchFilters:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise RuntimeError("LangChain/Ollama packages are not installed") from exc
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    prompt = f"""You are the search interpreter for a recruiting pipeline. Return one JSON object only; no Markdown.
Use only these keys when needed: name, current_stage, stuck_stage, min_days_in_stage, moved_to_stage, moved_since, reached_stage, not_hired, exclude_rejected.
Valid stages are Applied, Screening, Interview, Offer, Hired, Rejected. Combine filters with AND. Omit unused keys.
Current UTC time is {now.isoformat()}. This week's Monday is {monday.isoformat()}. For 'since Monday', set moved_since to that exact ISO timestamp. For 'more than a week', use min_days_in_stage: 7.
For 'stuck in Screening', set stuck_stage to Screening and min_days_in_stage to the stated duration. For 'moved to Interview since Monday', set moved_to_stage to Interview and moved_since to the Monday timestamp.
For 'reached Offer but didn't get hired', set reached_stage to Offer and not_hired to true.
For 'everyone except rejected candidates', set exclude_rejected to true.
If filters are combined, include each supported constraint in the same JSON object. A bare short query such as 'MLE' is a fuzzy candidate name and should return {{"name":"MLE"}}.
Examples: "Who's in Interview right now?" -> {{"current_stage":"Interview"}}; "everyone except rejected candidates" -> {{"exclude_rejected":true}}.
Only when a request is clearly unrelated to candidates or pipeline search, return {{"invalid":"brief helpful explanation"}}.
Query: {query}"""
    response = ChatOllama(model=OLLAMA_MODEL, temperature=0, format="json").invoke(prompt)
    content = response.content if isinstance(response.content, str) else str(response.content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SearchParseError("Qwen returned malformed JSON for the search filters.") from exc
    if not isinstance(data, dict):
        raise SearchParseError("Qwen returned filters in an unexpected format.")
    if "invalid" in data:
        raise SearchParseError(str(data["invalid"]))
    try:
        return SearchFilters.model_validate(data)
    except ValidationError as exc:
        raise SearchParseError(f"Qwen returned incomplete or inconsistent filters: {exc}") from exc


def interpret_query(query: str) -> tuple[SearchFilters, str, str]:
    try:
        return parse_with_ollama(query), "ollama", "AI interpreted your search."
    except SearchParseError as model_error:
        # A model can reject a valid but terse name (for example, "MLE").
        # The deterministic parser is authoritative for simple name/pipeline forms.
        try:
            filters = parse_fallback(query)
        except SearchParseError:
            raise model_error
        return filters, "fallback", "Qwen could not produce a usable filter, so deterministic search rules were used instead."
    except Exception as exc:
        try:
            filters = parse_fallback(query)
        except SearchParseError as fallback_error:
            raise SearchParseError(f"AI interpretation is unavailable and the fallback could not understand this query: {fallback_error}") from exc
        return filters, "fallback", "AI interpretation is unavailable; deterministic search rules were used instead."
