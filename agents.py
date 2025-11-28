# Importing the required modules
from google.adk.agents import Agent, LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool
from google.genai import types
import asyncio
import os

import utils

from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter
from google.adk.tools.tool_context import ToolContext
from google.adk.code_executors import BuiltInCodeExecutor
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
        instruction = """You are a data validation agent. Your goal is to validate the CSV metadata file for correctness and completeness before it is inserted into the lab data management database.,
        You will be provided with a CSV file containing metadata about lab data files.  Your job is to check the following:
        1. Ensure all required fields are present and correctly formatted.
        2. Check for any missing or null values in critical fields.
        3. Validate data types for each field (e.g., dates, numbers, strings).
        4. Identify any duplicate records based on unique identifiers.
        You are ONLY allowed to use the "validate_csv" and "validate_analysis_metadata" function tools to perform the validation tasks.
        The user should provide you with a CSV "file path" and an "output path" for invalid records. These are the inputs of the function tool to be used. If the user does not provide these, ask them to do so.
        Call the validate_csv function tool to validate the regular metadata CSV. Call the validate_analysis_metadata function tool to validate the analysis metadata CSV. Do not mix them up. 
        If you receive any request outside of data validation, respond with "I am only allowed to perform data validation tasks. 
        The functions save the invalid records to the specified output path. But they also return them as a list of dictionaries.
        """,
        tools = [FunctionTool(data_validation.validate_csv), FunctionTool(data_validation.validate_analysis_metadata)],
        output_key = "invalid_rows"
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
        instruction = 
        """
            You are a helpful assistant that inserts data from a CSV file into a database
            using the provided `insert_from_csv` tool.

            Required tool arguments:
            - csv_path (string, path to CSV)
            - db_path (string, path or connection string)

            After calling the tool, summarize the number of skipped rows based on output_key.
        """,
        tools = [FunctionTool(func=insert_from_csv)],
        output_key="skipped_rows"
    )
except Exception as e:
    logger.error(f"Error creating insert agent: {e}")
    raise e
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
    You infere the "key-value" pairs from the user request. Once you infere the key and the corresponding value, you MUST output a python code that creates a dictionary called "filters" with the inferred key-value pairs.
    For example, if the user request is "Delete all records for organism E.coli and protein DnaA", you should output the following code:
    filters = {"organism": "E.coli", "protein": "DnaA"}. You MUST provide the output in the form of a dictionary ONLY. Do NOT include any other text or explanation before or after the code block.
    If a certain field is not mentioned in the user request, do NOT include it in the filters dictionary.
    If the user request is ambiguous respond with "The provided criteria is ambiguous. Please provide more specific details." 
    If the user provides the criteria but not the values for the fields, respond with "The provided criteria is incomplete. Please provide values for the specified fields."
    If the usr provides criteria that includes fields outside of the supported set, respond with "The provided criteria includes unsupported fields. Please use only the supported fields.
    If the user request is not related to filter inference, respond with "I am only allowed to infer filters for database operations."
    
    """,
    code_executor=BuiltInCodeExecutor(),
    output_key="filters"
)
# Agent for deleting records from the database

delete_agent = LlmAgent(
    name="delete_agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_config=retry_config),
    description="This agent deletes records from the database based on specified criteria.",
    instruction=
    """
        You are a helpful assistant that deletes records from a database.
        You MUST use the `decide_and_perform_delete_records` tool for this.
      
        Required tool arguments:
            - db_path (string)
            - table (string)
            - filters (string, optional SQL WHERE clause)

        After calling the tool, summarize the number of deleted records based on output_key.
    """,
    tools=[FunctionTool(func=utils.decide_and_perform_delete_records)],
    output_key="deleted_count"
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

# runners for the agents


async def main():

    #data_validation_runner = InMemoryRunner(agent = data_validation_agent)

    #response = await data_validation_runner.run_debug("Validate the regular metadata in the file /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal S/1s interval/metadata_complete.csv and save invalid records to /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal/invalid_rows.csv")

    #print("Data Validation Agent Response:")
    filter_infer_runner = InMemoryRunner(agent = filter_infer_agent)
    response = await filter_infer_runner.run_debug("all records for organism E.coli and protein DnaA")
    print(response)
    logger.info(f"Filter inference Response: {response}")

asyncio.run(main())

