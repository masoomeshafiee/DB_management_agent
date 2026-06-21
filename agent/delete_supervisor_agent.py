from __future__ import annotations

# Importing the required modules
from google.adk.agents import SequentialAgent

import logging

from . import filter_agent as filter_mod
from . import delete_agent as delete_mod

logger = logging.getLogger(__name__)



try:
    delete_supervisor_agent = SequentialAgent(
    name = "delete_supervisor_agent",
    sub_agents = [filter_mod.filter_infer_agent, delete_mod.delete_agent]
)
    logger.info("Created agent: %s", delete_supervisor_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_supervisor_agent: {e}")
    raise e
