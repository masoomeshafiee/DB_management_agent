from __future__ import annotations

# Importing the required modules
from google.adk.agents import SequentialAgent

import os
import logging

from . import filter_agent as filter_mod
from . import delete_agent as delete_mod
from . import utils

logging.basicConfig(
    filename = "./agent.log",
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    )
logger = logging.getLogger(__name__)
#audit_logger = logging.getLogger("db_management_agent.audit")



try:
    delete_supervisor_agent = SequentialAgent(
    name = "delete_supervisor_agent",
    sub_agents = [filter_mod.filter_infer_agent, delete_mod.delete_agent]
)
    logger.info("Created agent: %s", delete_supervisor_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_supervisor_agent: {e}")
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