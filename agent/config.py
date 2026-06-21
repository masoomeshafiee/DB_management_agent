from __future__ import annotations

import logging
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
# Logging — configured once when this module is first imported.
# All agent modules should only call logging.getLogger(__name__).
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="./agent.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
