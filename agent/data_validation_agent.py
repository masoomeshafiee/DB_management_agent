from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool
from google.genai import types

import os
import logging

from lab_data_manager import data_validation

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
# retry_config = types.HttpRetryOptions(attempts = 5, exp_base = 7, initial_delay = 1, http_status_codes = [429, 500, 503, 504])
retry_config = types.HttpRetryOptions(
    attempts=1,          # avoid burst retries on 429
    exp_base=2,
    initial_delay=10,
    http_status_codes=[429, 500, 503, 504],
)


# ----------------------------------------------------------------------------------------
# Sub agents
# ----------------------------------------------------------------------------------------

# Agent for validating data to be inserted in the database
prompt =   """
        You are a data validation agent. Your goal is to validate the CSV metadata file for correctness and completeness.

        **CRITICAL PATH INSTRUCTION:** You must pass the file path argument **EXACTLY** as the user provided it.
        - **Do NOT** add "./" to the beginning.
        - **Do NOT** convert absolute paths (starting with "/") to relative paths.
        - If the user writes "/Users/name/file.csv", you MUST send "/Users/name/file.csv" to the tool. 

        **CRITICAL WORKFLOW INSTRUCTION:** Even if the user asks to "Insert" or "Upload" a file, **your ONLY job is to validate it.** Do not refuse the request; simply run the validation tool.

        **TOOL SELECTION STRATEGY (CRITICAL):**
        Analyze the user's request to determine the type of data:
        
        1. **Regular / Experiment Metadata:**
        - Keywords: "regular data", "metadata", "experiment info", "standard".
        - ACTION: Call `validate_csv`.
        
        2. **Analysis / Result Metadata:**
        - Keywords: "analysis data", "results", "processed data", "analysis metadata".
        - ACTION: Call `validate_analysis_metadata`.
        
        *If the type is unclear, ask the user to clarify.*

        **OUTPUT PROTOCOL (STRICT):**
        Analyze the tool's return list (invalid_rows):
        
        1. IF the list is EMPTY (0 invalid rows): 
        Return: `validation_result = {PASS: "All records are valid. No invalid records found."}`

        2. IF the list is NOT EMPTY (Invalid rows found): 
        Return: `validation_result = {FAIL: "Validation failed. Found invalid rows. See output path."}`

        3. IF the file path or output path are missing:
        Return: `validation_result = {ERROR: "Missing required inputs."}`
    """

try: 
    data_validation_agent = Agent(
        name = "data_validation_agent",
        model = Gemini(model = "gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_options = retry_config),
        description = "An agent to validate  csv metadata file before inserting into the database.",
        instruction = prompt,
        tools = [FunctionTool(data_validation.validate_csv), FunctionTool(data_validation.validate_analysis_metadata)],
        output_key = "validation_result"
    )
    logger.info("Created agent: %s", data_validation_agent.name)
except Exception as e:
    logger.exception(f"Error creating data validation agent: {e}")
    raise e