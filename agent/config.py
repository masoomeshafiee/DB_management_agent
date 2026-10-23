from __future__ import annotations

import os

from dotenv import load_dotenv
from google.genai import types

# ---------------------------------------------------------------------------
# Load GOOGLE_API_KEY (and any other env vars) from .env before any agent
# module reads os.getenv("GOOGLE_API_KEY") at import time. This module must
# be imported before any agent that constructs a Gemini(...) model.
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Default database path, shared by every agent that needs one (query, delete,
# insert) so there's exactly one place that decides it — not each agent's own
# prompt or schema default. Resolved relative to this file, not the process
# cwd, so it works regardless of where the app is launched from.
# ---------------------------------------------------------------------------
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_data.db")

# ---------------------------------------------------------------------------
# Shared retry configuration for all Gemini agents
# ---------------------------------------------------------------------------
retry_config = types.HttpRetryOptions(
    attempts=1,       # avoid burst retries on 429
    exp_base=2,
    initial_delay=10,
    http_status_codes=[429, 500, 503, 504],
)

# ---------------------------------------------------------------------------
# Logging is configured once, centrally, by the entrypoint (main.py / server.py)
# via observability.logging_config.config_logging(). All agent modules should
# only call logging.getLogger(__name__).
# ---------------------------------------------------------------------------
