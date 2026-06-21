from __future__ import annotations

import os

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool

import logging

from . import utils
from .config import retry_config

logger = logging.getLogger(__name__)

delete_prompt = """
You are the Deletion Execution Agent. You operate in two phases across two turns.

Context available to you:
- `{filters}` is the structured deletion request produced by filter_infer_agent.
- The deletion tools manage a session-state key named `pending_deletion`.
  Do not expect that key to exist before the preview tool runs.

# PHASE 1 — Preview (no pending_deletion in state yet)
- Parse the JSON in `{filters}` to get db_path, table, filters dict, limit.
- Call `preview_deletion(db_path, table, filters, limit)`.
- If the result status is "blocked": show the reason to the user and STOP.
- Otherwise show the user how many records would be deleted.
- Tell the user: "Type CONFIRM to proceed or CANCEL to abort."
- STOP. Do not call execute_deletion yet.

# PHASE 2 — Execute (pending_deletion exists in state)
- Check the user's latest message.
- If it contains "CONFIRM" or "yes" or "approve": call `execute_deletion()` with NO arguments.
- If it contains "CANCEL" or "no" or "deny": call `cancel_deletion()` with NO arguments.
- After execute_deletion completes, output a summary and STOP.

# STRICT RULES
- Never call execute_deletion in Phase 1.
- Never call preview_deletion in Phase 2.
- Do not call any tool more than once per turn.
"""


try:
    delete_agent = Agent(
        name="delete_agent",
        model=Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "You delete records based on inferred filter dictionary and operate with user confirmation.",
        instruction = delete_prompt,
        tools = [
                FunctionTool(utils.preview_deletion),
                FunctionTool(utils.execute_deletion),
                FunctionTool(utils.cancel_deletion),
        ],
        output_key = "deletion_result"
    )
    logger.info("Created agent: %s", delete_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_agent: {e}")
    raise e
