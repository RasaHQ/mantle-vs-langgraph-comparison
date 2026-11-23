"""LangSmith setup. Off unless an API key is present.

The key is read from the environment or the gitignored ``.env``. It is never
logged. Tracing posts runs from a background thread inside the LangSmith
client, and the agent's usage ledger is recorded separately, so a missing
key does not change the token counts.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langsmith.utils import get_env_var

ENGINE = "langgraph_native"
PROJECT = "langgraph-native"
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def configure_tracing(env_file: Path | None = _ENV_FILE) -> bool:
    """Turns tracing on when ``LANGSMITH_API_KEY`` is set.

    Returns whether tracing is on. An existing ``LANGSMITH_PROJECT`` is kept.
    """
    if env_file is not None and env_file.is_file():
        load_dotenv(env_file)
    if not os.environ.get("LANGSMITH_API_KEY", "").strip():
        get_env_var.cache_clear()
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_PROJECT", PROJECT)
    get_env_var.cache_clear()
    return True
