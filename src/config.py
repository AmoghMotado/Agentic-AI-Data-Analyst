"""
Central settings. Reads secrets from the .env file so no key is ever hardcoded.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Loads OPENAI_API_KEY / OPENAI_MODEL from .env into environment variables
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "data" / "sales.db"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

# How many times the agent may ask the LLM to correct a failed query
MAX_RETRIES = 2

# Never return more than this many rows from one query (protects UI and LLM context)
MAX_ROWS = 200


def get_api_key():
    """Returns the OpenAI API key, or None if it is missing or still the placeholder."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or key == "sk-your-key-here":
        return None
    return key
