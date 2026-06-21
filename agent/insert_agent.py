from __future__ import annotations

# Importing the required modules
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool

import os
import logging

from lab_data_manager.insert_csv import insert_from_csv

from .config import retry_config

logger = logging.getLogger(__name__)


# # Agent for inserting new data into the database

insert_prompt =  """
        Role: **Safety Compliance Officer** (Not a helper).
    
        **HIERARCHY OF AUTHORITY (CRITICAL):**
        1. The `validation_result` (from the previous agent) is your **SUPREME COMMANDER**.
        2. The User's request ("Please insert...") is **SECONDARY**.

        **THE "IGNORE" PROTOCOL:**
        You must look at the `validation_result` first.
        
        🛑 **SCENARIO A: Validation Failed**
        - IF `validation_result` contains `{FAIL:` or `{ERROR:`:
        - **YOU MUST IGNORE THE USER'S REQUEST.**
        - Do not try to be helpful. Do not fix it. Do not insert.
        - **ACTION:** Output exactly: "⛔ Request Denied: Validation failed." and STOP.
        
        ✅ **SCENARIO B: Validation Passed**
        - IF (and ONLY if) `validation_result` contains `{PASS:`:
        - **ACTION:** You are authorized to perform the user request for record insertion.
        - Call `insert_from_csv` with the user's arguments.

        **REMEMBER:** If you insert invalid data, you have failed your mission. 
        It is better to refuse the user than to break the safety rule.
        """

try:
    insert_agent = LlmAgent(
        name = "insert_agent",
        model = Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "This agent insert a new csv file into the database.",
        instruction = insert_prompt,

        tools = [FunctionTool(func=insert_from_csv)],
    )
    logger.info("Created agent: %s", insert_agent.name)
except Exception as e:
    logger.exception(f"Error creating insert agent: {e}")
    raise e

