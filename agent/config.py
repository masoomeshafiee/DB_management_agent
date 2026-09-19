from __future__ import annotations

from google.genai import types

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
