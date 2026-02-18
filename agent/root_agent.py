from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.tools import AgentTool
from google.adk.models.google_llm import Gemini
from google.adk.apps.app import App, ResumabilityConfig, EventsCompactionConfig
from google.adk.plugins.logging_plugin import LoggingPlugin

from google.genai import types

import os
import logging
# Import sibling modules using relative imports
from . import delete_supervisor_agent as delete_mod
from . import insert_supervisor_agent as insert_mod

logging.basicConfig(
    filename = "./agent.log",
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    )
logger = logging.getLogger(__name__)
#audit_logger = logging.getLogger("db_management_agent.audit")

API_KEY = os.getenv("GOOGLE_API_KEY")

retry_config = types.HttpRetryOptions(
    attempts=1,          # avoid burst retries on 429
    exp_base=2,
    initial_delay=10,
    http_status_codes=[429, 500, 503, 504],
)


# ----------------------------------------------------------------------------------------
# ROOT AGENT
# ----------------------------------------------------------------------------------------
root_prompt = """
           You are the Lab Data Manager Router. You do NOT execute database operations.

            You are in sub_agents mode.
            The ONLY function/tool you may call is:
            - transfer_to_agent

            Sub-agents (use these names exactly):
            - delete_supervisor_agent
            - insert_supervisor_agent

            Routing:
            - If the user request is about deleting/removing records or rows, call:
            transfer_to_agent with args {"agent_name":"delete_supervisor_agent"}
            - If the user request is about inserting/uploading/importing data, call:
            transfer_to_agent with args {"agent_name":"insert_supervisor_agent"}
            - If intent is unclear, ask ONE clarifying question and do NOT call any tool.

            Output rules:
            - If routing, output ONLY the function call (no extra text).
            - After transfer, pass through the sub-agent output exactly as-is. Do not edit tool calls or arguments.

            Examples (must follow exactly):

            DELETE example:
            function_call: transfer_to_agent
            args: {"agent_name":"delete_supervisor_agent"}

            INSERT example:
            function_call: transfer_to_agent
            args: {"agent_name":"insert_supervisor_agent"}
        """
try:
    root_agent = Agent(
        name="root_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description="Root orchestrator for Laboratory Data Management.",
        instruction=root_prompt,
    
        # We use the specialist operation agents as sub-agents
        # Pass the actual Agent instances defined in the modules
        sub_agents=[insert_mod.insert_supervisor_agent, delete_mod.delete_supervisor_agent],
        # tools=[ AgentTool(agent=insert_mod.insert_supervisor_agent), AgentTool(agent=delete_mod.delete_supervisor_agent)]
        
    )
    logger.info("Root agent created successfully. Name:%s", root_agent.name)
except Exception as e:
    logger.exception(f"Error creating root agent: {e}")
    raise e

# create the root agent app to add persistence layer

try:
    db_manager_app = App(name = "db_manager_app",  
        root_agent = root_agent,
        resumability_config = ResumabilityConfig(is_resumable = True, storage_path = "./db_manager_app_state"),
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=5,  # Cleanup every 5 turns
            overlap_size=2),          # Keep the 2 newest messages, summarize the rest
        plugins=[LoggingPlugin()]
        )
    logger.info(f"DB Manager app: {db_manager_app.name} created successfully.")
except Exception as e:
    logger.exception("Error creating db_manager_app")
    raise e
    



# """
# You are the Lab Data Manager Orchestrator. Your job is to understand user requests and delegate tasks to the appropriate specialist agents.
# To perform the operations, you are ONLY allowed to call your espesialist listed bellow. You MUST not call any other tools nor performing the task yourself. 
# You have access to the following specialists:

# 1. insert_supervisor_agent: For adding new data from the CSV files to the database.
# 2. delete_supervisor_agent: For deleting records from the database.

# Rules:
# - You MUST analyze the user's request to determine the intent (insert vs delete) and delegate to the correct sub agent.
# - If a user asks to delete data, delegate to the 'delete_supervisor_agent'.
# - If a user asks to upload or insert data, delegate to the 'insert_supervisor_agent'.
# - If a sub-agent returns a function_call, you MUST NOT modify it. You MUST forward it exactly as-is in your own output.
# - Do NOT summarize or restate anything when the sub-agent uses a tool. Only pass through the function_call unchanged.
# - If a sub-agent emits a tool call, you MUST forward it exactly. Do NOT add your own text unless the sub-agent produced text.

# The user should provide you the necessary details for performing the operations.
# For the insert operation, the user must provide the file path of the CSV file to be inserted and the output path for saving invalid records (if any).
# For the delete operation, the user must provide the database path, the table to delete record from, and the criteria for selecting records to be deleted.(The criteria will be used to infer the filters by the filter_infer_agent internally).
# You get the "deletion_result" from the delete_supervisor_agent which includes the status of the deletion operation, a message and number of deleted/to_be_deleted records.
# """,