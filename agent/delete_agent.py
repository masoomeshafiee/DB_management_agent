from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import AgentTool, FunctionTool
from google.genai import types

import os
import logging

from . import filter_agent as filter_mod
from . import utils

logging.basicConfig(
    filename = "./agent.log",
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    )
logger = logging.getLogger(__name__)
#audit_logger = logging.getLogger("db_management_agent.audit")

API_KEY = os.getenv("GOOGLE_API_KEY")

# Configuring retry options for the agents
retry_config = types.HttpRetryOptions(
    attempts=1,          # avoid burst retries on 429
    exp_base=2,
    initial_delay=10,
    http_status_codes=[429, 500, 503, 504],
)

delete_prompt = """
            # ROLE
            You are the Delete Execution Officer. You handle a two-stage deletion process: 1) Preview (Dry Run) and 2) Actual Deletion.

            # OPERATING PROTOCOL
            1. **GET CONTEXT**: 
            - Recive "filters" python dictionary from the filter_infer_agent.
            - Extract the `db_path` and `table` name from the user's original request in the conversation history.

            2. **STAGE 1: THE PREVIEW (First Turn)**
            - If you have not called the tool yet, you MUST call `ask_for_deletion_confirmation` with the following arguments:
                - db_path (string)
                - table (string)
                - filters (python dictionary, inferrd from the user request by the filter_infer_agent)
                - limit (integer, optional, default is 10)
                - dry_run (boolean, optional, default is True).
            - Goal: Provide the user with a CSV of records that *would* be deleted.

            3. **STAGE 2: THE EXECUTION (After User Approval)**
            - Inspect the tool execution result from the previous turn.
            - IF the status is "approved": Call `ask_for_deletion_confirmation` again with with the following arguments:
                - db_path (string)
                - table (string)
                - filters (python dictionary, inferrd from the user request by the filter_infer_agent)
                - dry_run (boolean, `False`).
            - IF the status is "denied": Terminate and say "Deletion cancelled by user."
            - IF the status is "pending": Do nothing; wait for the system to resume.

            # CRITICAL CONSTRAINTS
            - **TOOL-ONLY OUTPUT**: When calling the tool, output ONLY the function call. No text.
            - **DATA INTEGRITY**: Use the exact `db_path` and `table` provided by the user. Do not guess or modify them.
            - **SAFETY**: Never set `dry_run=False` unless the tool result explicitly indicates user approval.

"""

try:
    delete_agent = Agent(
        name="delete_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description = "You delete records based on inferred filter dictionary and operate with user confirmation.",
        instruction = delete_prompt,
        tools = [
                 FunctionTool(utils.ask_for_deletion_confirmation, require_confirmation=True)],
        output_key = "deletion_result"
    )
    logger.info("Created agent: %s", delete_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_agent: {e}")
    raise e



# """ You are the Delete Operation Agent. Your job is to 
        # 1. FIRST ALWAYS recive "filters" python dictionary from the filter_infer_agent. 
        # 2. You MUST call the 'ask_for_deletion_confirmation' function with the function call with the following arguments:
        #         - db_path (string)
        #         - table (string)
        #         - filters (python dictionary, inferrd from the user request by the filter_infer_agent)
        #         - limit (integer, optional, default is 10)
        #         - dry_run (boolean, optional, default is True)
        #     Your output MUST be the function_call. Never respond in text.
        #     If the response status is "pending", you MUST wait for user confirmation before proceeding.
        #     If the response status is "approved", you MUST proceed with the deletion by calling the ask_for_deletion_confirmation tool as a function call with the dry_run=False.
        #     If the response status is "denied", you MUST cancel the deletion operation.

        #     When responding, you MUST output ONLY a function_call. No natural language. No summaries. No explanations.
        # """
# Delete supervisor agent