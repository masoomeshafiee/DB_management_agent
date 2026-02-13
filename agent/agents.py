from __future__ import annotations

# Importing the required modules
from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import AgentTool, FunctionTool
from google.adk.apps.app import App, ResumabilityConfig, EventsCompactionConfig
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.plugins.logging_plugin import LoggingPlugin

from google.genai import types

import os
import logging
import uuid

from . import utils

from lab_data_manager import data_validation
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter

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

try: 
    data_validation_agent = Agent(
        name = "data_validation_agent",
        model = Gemini(model = "gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_options = retry_config),
        description = "An agent to validate  csv metadata file before inserting into the database.",
        instruction = 
        """
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
    ,
        tools = [FunctionTool(data_validation.validate_csv), FunctionTool(data_validation.validate_analysis_metadata)],
        output_key = "validation_result"
    )
    logger.info("Created agent: %s", data_validation_agent.name)
except Exception as e:
    logger.exception(f"Error creating data validation agent: {e}")
    raise e

# # Agent for inserting new data into the database
try:
    insert_agent = LlmAgent(
        name = "insert_agent",
        model = Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description = "This agent insert a new csv file into the database.",
        instruction = """
        Role: **Safety Compliance Officer** (Not a helper).
    
        **HIERARCHY OF AUTHORITY (CRITICAL):**
        1. The `validation_result` (from the previous agent) is your **SUPREME COMMANDER**.
        2. The User's request ("Please insert...") is **SECONDARY**.

        **THE "IGNORE" PROTOCOL:**
        You must look at the `validation_result` first.
        
        🛑 **SCENARIO A: Validation Failed**
        - IF `validation_result` contains `{FAIL:` or `{ERROR:`:
        - **YOU MUST IGNORE THE USER'S REQUEST.**
        - Do not try to be helpful. Do not fix it. Do not insert.
        - **ACTION:** Output exactly: "⛔ Request Denied: Validation failed." and STOP.
        
        ✅ **SCENARIO B: Validation Passed**
        - IF (and ONLY if) `validation_result` contains `{PASS:`:
        - **ACTION:** You are authorized to perform the user request for record insertion.
        - Call `insert_from_csv` with the user's arguments.

        **REMEMBER:** If you insert invalid data, you have failed your mission. 
        It is better to refuse the user than to break the safety rule.
        """,

        tools = [FunctionTool(func=insert_from_csv)],
    )
    logger.info("Created agent: %s", insert_agent.name)
except Exception as e:
    logger.exception(f"Error creating insert agent: {e}")
    raise e


insert_supervisor_agent = SequentialAgent(
    name = "insert_supervisor_agent",
    sub_agents = [data_validation_agent, insert_agent]
)
logger.info("Created sequential agent: %s", insert_supervisor_agent.name)


# Agent for infering the filters from the user request 

try:
    filter_infer_agent = Agent(
        name = "filter_infer_agent",
        model = Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description = "An agent to infer SQL filters from user requests for the following delete/ search operations.",
        instruction = """ You are a filter inference agent. Your goal is to infer SQL filters from the user requests to be used in delete or search operations on the lab data management database.
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
        
        """,
        code_executor=BuiltInCodeExecutor(),
        output_key="filters"
    )
    logger.info("Created agent: %s", filter_infer_agent.name)
except Exception as e:
    logger.exception(f"Error creating filter_infer_agent: {e}")
    raise e


# Delete supervisor agent
try:
    delete_supervisor_agent = Agent(
        name="delete_supervisor_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description = "Supervisor agent to manage the filter inference and deletion operation with user confirmation.",
        instruction = """ You are the Delete Operation Supervisor. Your job is to 
        1. FIRST ALWAYS infer the filters from the user request ONLY by calling the filter_infer_agent tool. Pass it the entire user message. You should receive the "filters" dictionary as an output from that tool.
        3. Then you MUST call the 'ask_for_deletion_confirmation' function with the function call with the following arguments:
                - db_path (string)
                - table (string)
                - filters (dictionary, inferrd from the user request by the filter_infer_agent)
                - limit (integer, optional, default is 10)
                - dry_run (boolean, optional, default is True)
            Your output MUST be the function_call. Never respond in text.
            If the response status is "pending", you MUST wait for user confirmation before proceeding.
            If the response status is "approved", you MUST proceed with the deletion by calling the ask_for_deletion_confirmation tool as a function call with the dry_run=False.
            If the response status is "denied", you MUST cancel the deletion operation.

            When responding, you MUST output ONLY a function_call. No natural language. No summaries. No explanations.
        """,
        tools = [AgentTool(agent=filter_infer_agent), FunctionTool(utils.ask_for_deletion_confirmation, require_confirmation=True)],
        output_key = "deletion_result"
    )
    logger.info("Created agent: %s", delete_supervisor_agent.name)
except Exception as e:
    logger.exception(f"Error creating delete_supervisor_agent: {e}")
    raise e


# ----------------------------------------------------------------------------------------
# ROOT AGENT
# ----------------------------------------------------------------------------------------

try:
    root_agent = Agent(
        name="root_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description="Root orchestrator for Laboratory Data Management.",
        instruction="""
        You are the Lab Data Manager Orchestrator. Your job is to understand user requests and delegate tasks to the appropriate specialist agents.
        
        You have access to the following specialists:
        1. data_validation_agent: For checking CSV files before they are inserted into the database.
        2. insert_supervisor_agent: For adding new data from the CSV files to the database.
        3. delete_supervisor_agent: For deleting records from the database.

        Rules:
        - If a user asks to delete data, delegate to the 'delete_supervisor agent'.
        - If a user asks to upload or insert data, delegate to the 'insert_supervisor_agent'.
        - If a sub-agent returns a function_call, you MUST NOT modify it. You MUST forward it exactly as-is in your own output.
        - Do NOT summarize or restate anything when the sub-agent uses a tool. Only pass through the function_call unchanged.
        - If a sub-agent emits a tool call, you MUST forward it exactly. Do NOT add your own text unless the sub-agent produced text.

        The user should provide you the necessary details for performing the operations.
        For the insert operation, the user must provide the file path of the CSV file to be inserted and the output path for saving invalid records (if any).
        For the delete operation, the user must provide the database path, the table to delete record from, and the criteria for selecting records to be deleted.(The criteria will be used to infer the filters by the filter_infer_agent internally).
        You get the "deletion_result" from the delete_supervisor_agent which includes the status of the deletion operation, a message and number of deleted/to_be_deleted records.
        """,
        # We use the specialist operation agents as sub-agents
        sub_agents=[insert_supervisor_agent, delete_supervisor_agent],
        #tools=[AgentTool(agent=data_validation_agent), AgentTool(agent=insert_supervisor_agent), AgentTool(agent=delete_supervisor_agent)]
        
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
    