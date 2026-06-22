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
You receive a validated deletion request in `{filters}`.

1. Parse `{filters}`.
2. Call `preview_deletion` with db_path, table, filters, and limit.
3. Inspect the preview result.
4. If the result is blocked or has no matching records, report it and stop.
5. Otherwise call `execute_deletion` with no arguments.
6. The platform will pause `execute_deletion` and ask the user to approve or
   reject the operation using the preview result.
7. After the confirmation response, report the execution or cancellation result.
8. Never pass or reconstruct filters during execution.
"""

try:
    delete_agent = Agent(
        name="delete_agent",
        model=Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "You delete records based on inferred filter dictionary and operate with user confirmation.",
        instruction = delete_prompt,
        tools = [
            FunctionTool(utils.preview_deletion),
            FunctionTool(
                utils.execute_deletion,
                require_confirmation=True,
            ),
        ],
        output_key = "deletion_result"
    )
    logger.info("Created agent: %s", delete_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_agent: {e}")
    raise e
