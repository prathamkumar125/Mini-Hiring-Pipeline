# Mini Hiring Pipeline

A local recruiting app for tracking candidates through one job pipeline and finding them with natural-language search.

<img width="2866" height="1448" alt="image" src="https://github.com/user-attachments/assets/08313dc0-bfd0-40e9-822e-c4e0256f546b" />


## Steps to run

Open PowerShell in the project folder. Install [uv](https://docs.astral.sh/uv/) if needed, then create the environment and install the project dependencies:

```powershell
uv venv venv
uv pip install --python venv\Scripts\python.exe -r requirements.txt
```

Create the local configuration file and pull the configured Ollama model:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
ollama pull qwen2.5-coder:1.5b
```

The copy command preserves an existing `.env` so it does not replace local settings.

Ollama must be running locally. The Windows Ollama app normally starts its service; if it is not running, start it with `ollama serve`. Set `OLLAMA_MODEL` in `.env` to another model shown by `ollama list` if desired.

Start the API and UI in two separate PowerShell windows, both opened in the project folder:

```powershell
.\venv\Scripts\uvicorn.exe app.main:app --reload
```

```powershell
.\venv\Scripts\streamlit.exe run streamlit_app.py
```

Open the Streamlit URL printed in its terminal (usually `http://localhost:8501`). FastAPI’s interactive API documentation is at `http://127.0.0.1:8000/docs`.

The default database is `hiring_pipeline.db` in the working directory. Configuration is loaded from `.env` and can be overridden by environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `hiring_pipeline.db` | SQLite database location |
| `OLLAMA_MODEL` | `llama3.2` | Installed local model used to interpret searches; the supplied `.env.example` selects `qwen2.5-coder:1.5b` |
| `API_URL` | `http://127.0.0.1:8000` | FastAPI URL used by Streamlit |

Run the automated checks with:

```powershell
.\venv\Scripts\python.exe -m pytest
```

## Architecture summary

```text
Streamlit UI  ──HTTP──>  FastAPI routes  ──>  lifecycle / search services
                              │                         │
                              └──── repository ─────────┴──> SQLite
                                      │
Search request ──> LangChain / Ollama ──> validated filter model ──> parameterized query
                                      └──> supported local fallback when AI is unavailable
```

- `streamlit_app.py` presents the stage board, candidate form and detail history, submitted search results, and stored search logs.
- `app/main.py` exposes the REST API. `app/lifecycle.py` enforces candidate transitions; `app/search.py` interprets searches; `app/repository.py` reads and writes records; `app/database.py` creates the SQLite schema; and `app/domain.py` defines validated data models.
- SQLite stores candidate details, append-only stage events, and search logs. Current stage and time in stage are derived from the latest event.
- Search sends the query through LangChain to the configured Ollama model. The response must validate as a `SearchFilters` model; application code builds parameterized SQL from those filters and never executes model-provided SQL. If the model is unavailable or returns unusable filters, supported deterministic patterns and fuzzy name matching are used and the UI says so.

## Decisions and reasons

- **Append-only stage events:** candidate stage is derived from history, and SQLite triggers reject edits or deletion of recorded events. This preserves the audit trail while keeping the current stage easy to calculate.
- **Transitions enforced by the API:** a candidate can move only to the next stage or to Rejected from an active stage. Hired and Rejected are final. The write uses a SQLite transaction so simultaneous requests cannot advance the same candidate twice from a stale stage.
- **Separate UI and API:** Streamlit focuses on recruiter workflows; FastAPI owns rules and persistence. This keeps lifecycle rules consistent for both the UI and direct API clients.
- **Validated AI filters, not generated SQL:** Qwen translates the question into a small typed filter object. The repository applies those filters with parameterized queries, limiting the model’s authority and keeping execution predictable.
- **Local fallback and logs:** name matching and documented query patterns remain available if Ollama is down. Each search records its text, parser source, interpretation, result count, message, and timestamp in SQLite so the recruiter can inspect recent AI-assisted searches.
- **SQLite for v1:** the app is a single-recruiter local tool; SQLite keeps setup lightweight and requires no separate database service.

## Search examples

- `sharam` — fuzzy name match for Priya Sharma.
- `Who's in Interview right now?`
- `stuck in Screening for more than a week`
- `moved to Interview since Monday`
- `reached the Offer stage but didn't get hired`
- `everyone except rejected candidates`

Queries can combine a candidate name with pipeline filters. Unsupported or nonsensical requests return an explanation rather than being treated as a valid search with no matches.

## Over time

Add authentication, support multiple jobs, provide data migrations and deployment configuration, improve relative-date and fallback query coverage, and add configurable retention for search logs. Candidate profile edits would need their own immutable audit events.
