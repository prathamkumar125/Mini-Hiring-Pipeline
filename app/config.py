"""Application configuration loaded from environment variables and an optional .env file."""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Loads a project-root .env file when present without replacing real environment values.
load_dotenv()


DATABASE_PATH = os.getenv("DATABASE_PATH", "hiring_pipeline.db")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
