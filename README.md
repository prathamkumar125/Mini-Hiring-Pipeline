# Mini Hiring Pipeline

A local recruiter tool for one job pipeline. FastAPI owns the business rules and SQLite audit data; Streamlit provides the UI. Search uses LangChain + a local Ollama model when available, and a transparent deterministic fallback when it is not.

## Run it

1. Install [uv](https://docs.astral.sh/uv/) if needed, create the local environment, and install dependencies into it:
   ```bash
   uv venv venv
   venv\Scripts\activate
   uv pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and adjust configuration if needed. `python-dotenv` loads it automatically without overriding real environment variables.
3. AI interpretation: install [Ollama](https://ollama.com), start its local service, then pull the configured model (default in `.env.example`: `ollama pull qwen2.5-coder:1.5b`). Keep `OLLAMA_MODEL` set to a model that `ollama list` shows as installed.
4. Start the API in one terminal: `uv run --active uvicorn app.main:app --reload`
5. Start the UI in another: `uv run --active streamlit run streamlit_app.py`
6. Open the URL Streamlit displays (normally `http://localhost:8501`). The API is at `http://127.0.0.1:8000`; set `API_URL` if it differs. Set `DATABASE_PATH` to place the SQLite file elsewhere.

Run checks with `venv\Scripts\python.exe -m pytest`. The API’s interactive documentation is available at `/docs`.

## Design decisions

- **Append-only audit trail:** stage is derived from the latest event; events have SQLite triggers that abort updates and deletes. This prevents accidental history rewrites even outside the API.
- **Server-side state machine:** only the immediate next pipeline stage is valid. Rejection is allowed only from active stages; Hired and Rejected are terminal.
- **Safe natural-language search:** the model is asked for JSON matching a Pydantic schema, never SQL. The repository builds parameterized queries, and fuzzy ranking is performed in Python.
- **Graceful model outage:** every query is sent to LangChain/Ollama first. If Ollama is unavailable or returns invalid/unsupported filters, supported phrase patterns and fuzzy name matching continue to work and the UI identifies the fallback.
- **Local searchable AI log:** every search records its input, interpreted filters, parser source, outcome message, count, and timestamp in SQLite.

Example searches: `sharam`, `Who's in Interview right now?`, `stuck in Screening for more than a week`, `moved to Interview since Monday`, `reached the Offer stage but didn't get hired`, and `everyone except rejected candidates`.

## Improvements

Add authentication and role permissions, multiple jobs and candidate editing with a separate immutable change audit, pagination, richer relative-date parsing, configurable retention/redaction for search logs, background model-health checks, migration tooling, accessibility refinement, and deployment/container configuration.