from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.apps.app import App, ResumabilityConfig, EventsCompactionConfig
from google.adk.plugins.logging_plugin import LoggingPlugin

import os
import logging

# Import sibling modules using relative imports
from . import delete_supervisor_agent as delete_mod
from . import insert_supervisor_agent as insert_mod
from . import query_agent as query_mod
from .config import retry_config

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------------------
# ROOT AGENT

root_prompt = """
You are a Traffic Controller. Your only job is to route the user's request
using the `transfer_to_agent` tool.

# WORKER ASSIGNMENT RULES
- For removing or deleting records, transfer to "delete_supervisor_agent".
- For adding, uploading, or inserting data, transfer to "insert_supervisor_agent".
- For reading, searching, listing, counting, or finding records, transfer to
  "query_agent".

# CONSTRAINTS
- You cannot perform database operations yourself.
- Use only `transfer_to_agent`.
- Do not extract or modify data from the request.
"""


try:
    root_agent = Agent(
        name="root_agent",
        model=Gemini(model="gemini-2.5-flash", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description="Root orchestrator for Laboratory Data Management.",
        instruction=root_prompt,
    
        # We use the specialist operation agents as sub-agents
        # Pass the actual Agent instances defined in the modules
        sub_agents=[
            insert_mod.insert_supervisor_agent,
            delete_mod.delete_supervisor_agent,
            query_mod.query_agent,
        ],
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
