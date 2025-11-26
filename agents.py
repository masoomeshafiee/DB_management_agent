# Importing the required modules
from google.adk.agents import Agent, LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool
from google.genai import types
import asyncio
import os


from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
import logging

# configuring the logging
logging.basicConfig(filename = "/Users/masoomeshafiee/Projects/agent.log", level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger(__name__)



# Configuring retry options for the agents
retry_config = types.HttpRetryOptions(attempts = 5, exp_base = 7, initial_delay = 1, http_status_codes = [429, 500, 503, 504])



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
# ----------------------------------------------------------------------------------------


# runners for the agents


async def main():

    data_validation_runner = InMemoryRunner(agent = data_validation_agent)

    response = await data_validation_runner.run_debug("Validate the regular metadata in the file /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal S/1s interval/metadata_complete.csv and save invalid records to /Volumes/Masoumeh/Masoumeh/Masoumeh_data/1-Rfa1/dwell time/normal/invalid_rows.csv")

    print("Data Validation Agent Response:")
    print(response)
    logger.info(f"Data Validation Agent Response: {response}")

asyncio.run(main())

