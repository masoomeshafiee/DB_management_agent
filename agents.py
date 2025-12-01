# Importing the required modules
from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool
from google.genai import types
from google.adk.session import InMemorySessionService
import asyncio
import os
from typing import Dict, Any
import uuid
import utils

from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter
from google.adk.tools.tool_context import ToolContext
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.apps.app import App, ResumabilityConfig
import logging

# configuring the logging
logging.basicConfig(filename = "./agent.log", level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger(__name__)



# Configuring retry options for the agents
# retry_config = types.HttpRetryOptions(attempts = 5, exp_base = 7, initial_delay = 1, http_status_codes = [429, 500, 503, 504])
retry_config = types.HttpRetryOptions(
    attempts=1,          # avoid burst retries on 429
    exp_base=2,
    initial_delay=10,
    http_status_codes=[429, 500, 503, 504],
)


# ----------------------------------------------------------------------------------------
# Defining the sub agents for different DB operations 
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
    logger.info("Data validation agent created successfully.")
except Exception as e:
    logger.error(f"Error creating data validation agent: {e}")
    raise e

# Agent for inserting new data into the database
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
except Exception as e:
    logger.error(f"Error creating insert agent: {e}")
    raise e


insert_supervisor_agent = SequentialAgent(
    name = "insert_supervisor_agent",
    sub_agents = [data_validation_agent, insert_agent]
)


# Agent for infering the filters from the user request 
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
    You infere the "key-value" pairs from the user request. Once you infere the key and the corresponding value, you MUST output a python code that creates a dictionary called "filters" with the inferred key-value pairs.
    For example, if the user request is "Delete all records for organism E.coli and protein DnaA", you should output the following:
    filters = {"organism": "E.coli", "protein": "DnaA"}. You MUST provide the output in the form of a dictionary ONLY. Do NOT include any other text or explanation before or after the code block.
    If a certain field is not mentioned in the user request, do NOT include it in the filters dictionary.
    If the user request is ambiguous your code MUST output {error: "The provided criteria is ambiguous. Please provide more specific details." }
    If the user provides the criteria but not the values for the fields, your code MUST output {error: "The provided criteria is incomplete. Please provide values for the specified fields."}
    If the usr provides criteria that includes fields outside of the supported set, your code MUST output {error:"The provided criteria includes unsupported fields. Please use only the supported fields.}
    If the user request is not related to filter inference, your code MUST output {error:"I am only allowed to infer filters for database operations."}
    
    """,
    code_executor=BuiltInCodeExecutor(),
    output_key="filters"
)
#--------------------------------------------------------------------------------
# Agent for deleting records from the database
#--------------------------------------------------------------------------------
# sub-agent tp perform the delete operation
delete_agent = LlmAgent(
    name="delete_agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
    description="This agent deletes records from the database based on specified criteria.",
    instruction=
    """
        You are a helpful assistant that deletes records from a database.
        You MUST use the `decide_and_perform_delete_records` tool for this.
        When you receive a deletion request, the filter_infer_agent must have already infered the filters from the user request first. So you will receive the filters dictionary as an input argument.
        Then you do the following steps:
        1. You MUST call the 'ask_for_deletion_confirmation' tool with the following arguments:
            - db_path (string)
            - table (string)
            - filters (dictionary, inferrd from the user request by the filter_infer_agent)
            - limit (integer, optional, default is 10)
            - dry_run (boolean, optional, default is True)
        2. If the response status is "pending", you MUST wait for user confirmation before proceeding.
        3. If the response status is "approved", you MUST proceed with the deletion using the ask_for_deletion_confirmation tool.
        4. If the response status is "denied", you MUST cancel the deletion operation.

        After calling the tool, summarize the result and number of deleted records based on output_key.
    """,
    tools=[FunctionTool(func=utils.ask_for_deletion_confirmation)],
    output_key="deleted_count"
)
# create a session service to manage sessions
session_service = InMemorySessionService()

# Wrap the deletion agent in the App which adds a persistence layer that saves and restores state.
deletion_app = App(
    name = "deletion_app",
    root_agent = delete_agent,
    resumability_config = ResumabilityConfig(is_resumable = True, storage_path = "./deletion_app_state")
)
logger.info("Deletion agent and app created successfully.")

# function to orchestrate the entire deletion approval flow.
async def run_deletion_workflow(user_request: Dict[str,Any], db_path:str, table:str, filters:Dict[str, Any], limit:int=10, dry_run:bool=True)->Dict[str, Any]:
    """
    Orchestrates the deletion workflow by first asking for user confirmation and then proceeding based on the response.
    """
    # create a unique session id 
    session_id = f"deletion_session_{uuid.uuid4().hex[:8]}"

    # create the session
    await session_service.create_session(app_name = deletion_app.name,user_id ="default_user", session_id = session_id)


    query_content = types.Content(role="user", parts=[types.Part(text=user_request)])
    events = []

    async for event in deletion_app.run(
        session_service = session_service,
        session_id = session_id,
        query_content = query_content,
        tools_args = {
            "ask_for_deletion_confirmation": {
                "db_path": db_path,
                "table": table,
                "filters": filters,
                "limit": limit,
                "dry_run": dry_run
            }
        }
    approval_info = check_for_approval(events)

    if approval_info:
        print(f"⏸️  Pausing for approval...")
        print(f"🤔 Human Decision: {'APPROVE ✅' if auto_approve else 'REJECT ❌'}\n")
    
        async for event in deletion_app.run_async(user_id="default_user", session_id=session_id, query_content=query_content, tools_args={
            "db_path": db_path,
            "table": table,
            "filters": filters,
            "limit": limit,
            "dry_run": dry_run,
            "approval_info": approval_info
            ), 
            invocation_id=approval_info[
                    "invocation_id"
                ],
        ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            print(f"Agent > {part.text}")
        else:
            for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")
            


# supervisor agent to manage the filter inference and subsequent delete operation with confirmation
delete_supervisor_agent = SequentialAgent(
    name = "delete_supervisor_agent",
    sub_agents = [filter_infer_agent, delete_agent]
)


# ----------------------------------------------------------------------------------------
# 2. DEFINE ROOT AGENT
# ----------------------------------------------------------------------------------------

try:
    root_agent = Agent(
        name="root_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
        description="Root orchestrator for Laboratory Data Management.",
        instruction="""
        You are the Lab Data Manager Orchestrator. Your job is to understand user requests and delegate tasks to the appropriate specialist agents.
        
        You have access to the following specialists:
        1. data_validation_agent: For checking CSV files before they are touched.
        2. insert_agent: For adding new data to the database.
        3. delete_agent: For removing records from the database.

        Rules:
        - If a user asks to delete data, delegate to the 'delete_agent'.
        - If a user asks to upload or insert data, first ask if they want to validate it. If yes, call 'data_validation_agent', then 'insert_agent'.
        - Always report back the final status from the specialist agent.
        """,
        # We wrap the sub-agents as tools here
        tools=[
            AgentTool(data_validation_agent),
            AgentTool(insert_agent),
            AgentTool(delete_agent)
        ]
    )
    logger.info("Root agent created successfully.")
except Exception as e:
    logger.error(f"Error creating root agent: {e}")
    raise e

# ----------------------------------------------------------------------------------------

# # runners for the agents


# async def main():

#     #data_validation_runner = InMemoryRunner(agent = data_validation_agent)

#     #response = await data_validation_runner.run_debug("Validate the regular metadata in the file /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal S/1s interval/metadata_complete.csv and save invalid records to /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal/invalid_rows.csv")

#     #print("Data Validation Agent Response:")
#     filter_infer_runner = InMemoryRunner(agent = filter_infer_agent)
#     response = await filter_infer_runner.run_debug("all records for organism E.coli after the date 20220101 with protein DnaA and dye concentration value 10 nM")
#     print(response)
#     logger.info(f"Filter inference Response: {response}")

# asyncio.run(main())

async def main():
    runner = InMemoryRunner(agent=insert_supervisor_agent)
    response = await utils.run_with_backoff(
        runner,
        "Please insert the regular data from '/Users/niushamirhakimi/Documents/code/llm/google5/DB_management_agent/test/metadata_complete_insert.csv' into the database located at 'data/lab_data.db', and save  invalid records to './invalid_rows.csv'."
    )
    #"./test/metadata_complete_insert.csv"
    print(response)

# ...existing code...

asyncio.run(main())