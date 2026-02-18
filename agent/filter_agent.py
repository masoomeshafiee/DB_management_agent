from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai import types
from google.adk.code_executors import BuiltInCodeExecutor

import os
import logging

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

# Agent for infering the filters from the user request 
filter_prompt = """ You are a filter inference agent. Your goal is to infer SQL filters from the user requests to be used in delete or search operations on the lab data management database.
        The user will provide you with a criteria in natural laguage for selecting records for further operations. But this criteria needs to be converted to a dictionary with a certain format to be uased by the other agents responsible for doing
        the database operations. The filter dictionary should have the following format:
        field_name: value, where field_name is the name of the column in the database table and value is the value to filter by.
        But we only have the limited set of filters that are supported. You should ONLY use the following fields/key for creating the filters dictionary:
        organism, protein, strain, condition, user_name, concentration_value, concentration_unit, capture_setting_id,capture_type, exposure_time, time_interval, is_valid,
        dye_concentration_value, dye_concentration_unit, date, replicate, experiment_id, raw_file_id, raw_file_name, tracking_file_id, mask_id, analysis_file_id, analysis_result_id, raw_file_type,
        mask_type, mask_file_type, analysis_file_type,analysis_result_type, comment, email. 
        These are the keys that are supported by the database schema. You should NOT use any other fields for creating the filters dictionary.
        Also make sure to use the EXACT field names as they are in the database schema. Do NOT use any synonyms or variations(such as upper case, etc.) of the field names.
        For the values you should use exactly what the user provides with the exception of the following fields for which you should follw the determined format for certain fields:
        1. date: "YYYYMMDD" (as a string, e.g., "20230915")
        2. exposure_time, time_interval : in seconds (float)
        3. condition_unit, concentration_unit: use the abbreviations such as "nM", "uM", "mM", etc.
        Output format:
            - Return ONLY a single Python dictionary literal.
            - NO backticks, NO code fences, NO explanation, NO extra text.
            - Example: if the user request is "Delete all records for organism E.coli and protein DnaA", you should output the following:
                {"organism": "E.coli", "protein": "DnaA"}
        If a certain field is not mentioned in the user request, do NOT include it in the filters dictionary.
        If the user request is ambiguous you MUST output {error: "The provided criteria is ambiguous. Please provide more specific details." }
        If the user provides the criteria but not the values for the fields, you MUST output {error: "The provided criteria is incomplete. Please provide values for the specified fields."}
        If the usr provides criteria that includes fields outside of the supported set, you MUST output {error:"The provided criteria includes unsupported fields. Please use only the supported fields.}
        If the user request is not related to filter inference, your MUST output {error:"I am only allowed to infer filters for database operations."}
        
        """
try:
    filter_infer_agent = Agent(
        name = "filter_infer_agent",
        model = Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "An agent to infer SQL filters from user requests for the following delete/ search operations.",
        instruction = filter_prompt,
        code_executor=BuiltInCodeExecutor(),
        output_key="filters"
    )
    logger.info("Created agent: %s", filter_infer_agent.name)
except Exception as e:
    logger.exception(f"Error creating filter_infer_agent: {e}")
    raise e