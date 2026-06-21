from __future__ import annotations

import logging
import os

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool

from . import utils
from .config import retry_config

logger = logging.getLogger(__name__)

confirmation_prompt = """
You handle responses to a previously previewed deletion.

- If the latest user message approves the deletion, call `execute_deletion`.
- If the latest user message cancels or rejects the deletion, call `cancel_deletion`.
- Call exactly one tool with no arguments.
- Never reconstruct, modify, or invent deletion filters.
- After the tool returns, summarize its result briefly.
"""

try:
    deletion_confirmation_agent = Agent(
        name="deletion_confirmation_agent",
        model=Gemini(
            model="gemini-2.5-flash-lite",
            api_key=os.getenv("GOOGLE_API_KEY"),
            retry_config=retry_config,
        ),
        description="Confirms or cancels a deletion already stored in session state.",
        instruction=confirmation_prompt,
        tools=[
            FunctionTool(utils.execute_deletion),
            FunctionTool(utils.cancel_deletion),
        ],
    )
    logger.info("Created agent: %s", deletion_confirmation_agent.name)
except Exception as e:
    logger.exception("Error creating deletion_confirmation_agent: %s", e)
    raise
