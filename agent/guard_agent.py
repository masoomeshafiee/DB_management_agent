from __future__ import annotations

import os
import logging

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

from .config import retry_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guard Agent
#
# Sits between filter_infer_agent and delete_agent in the SequentialAgent
# pipeline. Its only job is to inspect the structured filter schema produced
# by filter_infer_agent and decide whether the delete operation is safe to
# proceed. It writes one of two outcomes to the "guard_result" session key:
#
#   PROCEED  — schema is valid, table is identified, operation can continue.
#   BLOCKED  — schema is missing critical fields or is dangerously broad;
#              delete_agent will read this and abort without touching the DB.
# ---------------------------------------------------------------------------

guard_prompt = """
You are a Safety Guard Agent. You sit between the Filter Agent and the Delete Agent.
Your ONLY job is to inspect the JSON string stored in `{filters}` and decide whether
the delete operation is safe to proceed.

`{filters}` is a JSON string like:
{"db_path": "...", "table": "TrackingFiles", "filters": {"date": "20230803"}, "limit": null}

# DECISION RULES

BLOCK (output "BLOCKED: <reason>") if ANY of the following are true:
1. `{filters}` is empty, null, or not valid JSON.
2. The `table` field is missing or empty.
3. The `filters` object is empty ({}) — no criteria means deleting the whole table.
4. The JSON contains an "error" key.

PROCEED (output "PROCEED") if ALL of the following are true:
- `table` is a non-empty string.
- `filters` contains at least one key-value pair.

# OUTPUT FORMAT (STRICT)
Output ONLY one of:
- PROCEED
- BLOCKED: <short reason>

No extra text.
"""

try:
    guard_agent = Agent(
        name="guard_agent",
        model=Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_options=retry_config),
        description="Safety gate between filter parsing and deletion execution. Blocks unsafe or malformed delete requests before they reach the database.",
        instruction=guard_prompt,
        output_key="guard_result",
    )
    logger.info("Created agent: %s", guard_agent.name)
except Exception as e:
    logger.exception("Error creating guard_agent: %s", e)
    raise e
