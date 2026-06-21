from __future__ import annotations

# Importing the required modules
from google.adk.agents import SequentialAgent

import logging

from . import data_validation_agent as validation_mod
from . import insert_agent as insert_mod

logger = logging.getLogger(__name__)

insert_supervisor_agent = SequentialAgent(
    name = "insert_supervisor_agent",
    sub_agents = [validation_mod.data_validation_agent, insert_mod.insert_agent]
)
logger.info("Created sequential agent: %s", insert_supervisor_agent.name)