from __future__ import annotations

# Importing the required modules
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool

import os
import logging

from .config import retry_config
from .utils import insert_csv_with_report

logger = logging.getLogger(__name__)


# # Agent for inserting new data into the database

insert_prompt =  """
        You insert a validated CSV file into the database.

        Always call `insert_csv_with_report` with the CSV path from the user's
        request. Do not decide yourself whether the file passed validation, and
        do not go by earlier messages: the tool checks in code that this exact
        file passed validation in this session, and refuses it otherwise.

        Then report the tool's result as it is: the inserted and skipped counts,
        or, if it was blocked, that nothing was inserted and why.

        **NEVER GUESS THE DATABASE PATH:**
        `csv_path` and `db_path` are different files. If the user doesn't
        name a database, **omit `db_path`** (it defaults on its own) — never
        fill it in yourself, and never reuse `csv_path` as `db_path`.
        """

try:
    insert_agent = LlmAgent(
        name = "insert_agent",
        model = Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_options=retry_config),
        description = "This agent insert a new csv file into the database.",
        instruction = insert_prompt,

        tools = [FunctionTool(func=insert_csv_with_report)],
    )
    logger.info("Created agent: %s", insert_agent.name)
except Exception as e:
    logger.exception(f"Error creating insert agent: {e}")
    raise e

