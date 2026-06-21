from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

import os
import logging
from datetime import datetime

from .config import retry_config
from .pydantic_models import DeletionSchema

logger = logging.getLogger(__name__)

# Agent for infering the filters from the user request 
# Dynamically fetch the date for accurate relative date resolution
current_date = datetime.now().strftime("%B %d, %Y")

filter_prompt = f"""
You are an expert Data Extraction Agent for a laboratory database system.
Your objective is to extract the target table name and filtering criteria from the user's natural language request and output them as a JSON object.

# CURRENT SYSTEM CONTEXT
- Today's date is: {current_date}. Use this to resolve relative dates like "yesterday" or "last Tuesday".

# OUTPUT FORMAT (STRICT)
Output ONLY a valid JSON object with this exact structure — no backticks, no explanation, no extra text:
{{"db_path": "<path from user or ./data/sample_data.db>", "table": "<TableName>", "filters": {{"field": "value"}}, "limit": 10}}

# TABLE NAMES (use exactly as written)
AnalysisFiles, AnalysisResultExperiment, AnalysisResults, CaptureSetting,
Condition, Experiment, ExperimentAnalysisFiles, Masks, Organism,
Protein, RawFiles, TrackingFiles, User

# FILTER KEYS (use only these exact keys)
organism, protein, strain, condition, user_name, email, comment,
capture_setting_id, capture_type, replicate, experiment_id,
raw_file_id, raw_file_name, tracking_file_id, mask_id, analysis_file_id,
analysis_result_id, raw_file_type, mask_type, mask_file_type,
analysis_file_type, analysis_result_type, is_valid,
date (YYYYMMDD string), exposure_time (float seconds), time_interval (float seconds),
concentration_unit (nM/uM/mM/M), concentration_value (float),
dye_concentration_unit, dye_concentration_value (float)

# EXTRACTION RULES
1. Convert all dates to YYYYMMDD string format.
2. Convert all time values strictly to seconds (float).
3. Only include filters explicitly mentioned — do not guess defaults.
4. If the request is dangerously ambiguous (e.g. "delete everything"), output an empty filters dict: {{}}.
5. If the request does not provide usable deletion criteria, keep `filters` empty so the deletion safety layer blocks it.
6. If the latest message is a confirmation or cancellation such as "APPROVED",
   "CONFIRM", "yes", "CANCEL", "no", or "deny", reuse the table, database path,
   filters, and limit from the most recent deletion request in the conversation.
   Do not replace the previous filters with an empty object.
"""

try:
    filter_infer_agent = Agent(
        name = "filter_infer_agent",
        model = Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "An agent to infer SQL filters from user requests for the following delete/ search operations.",
        instruction = filter_prompt,
        output_schema=DeletionSchema,
        output_key="filters"
    )
    logger.info(
        "Created agent: %s with output schema: %s",
        filter_infer_agent.name,
        DeletionSchema.__name__,
    )
except Exception as e:
    logger.exception(f"Error creating filter_infer_agent: {e}")
    raise e
