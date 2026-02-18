from __future__ import annotations

# Importing the required modules
from google.adk.agents import SequentialAgent

import os
import logging

from . import data_validation_agent as validation_mod
from . import insert_agent as insert_mod

logging.basicConfig(
    filename = "./agent.log",
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    )
logger = logging.getLogger(__name__)

insert_supervisor_agent = SequentialAgent(
    name = "insert_supervisor_agent",
    sub_agents = [validation_mod.data_validation_agent, insert_mod.insert_agent]
)
logger.info("Created sequential agent: %s", insert_supervisor_agent.name)