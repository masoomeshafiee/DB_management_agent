import asyncio
import os
import glob
import logging
import traceback

#from agent import utils
from google.adk.runners import Runner
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.sessions import DatabaseSessionService

from agent.agents import db_manager_app
from workflow import run_db_workflow

from observability.logging_config import config_logging

# Set the App-level logger: 
logger = logging.getLogger("db_management_agent")

# Define where the database file will live
DB_FOLDER = "db_manager_app_state"
DB_FILE = "sessions.db"

def get_session_name():

    """Ask the user to provide a session name"""

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    logger.info(f"The sessions are stored in the session database file located at {DB_FOLDER}/{DB_FILE}")
    

    choice = input("Enter a session name to load or create (leave empty for default session): ").strip()

    session_name = choice if choice else "default"
    logger.info(f"Selected session name: {session_name}")

    return session_name


async def main():

    config_logging(level="INFO")

    logger.info("Starting Database Management Agent")

    db_path = os.path.join(DB_FOLDER, DB_FILE)
    db_url = f"sqlite+aiosqlite:///{db_path}"

    session_service = DatabaseSessionService(db_url)
    session_name = get_session_name()
    

    try:
 
        await session_service.create_session(
            app_name=db_manager_app.name,
            user_id="default_user",
            session_id=session_name
        )
        logger.info(f"Session '{session_name}' created or loaded successfully.")
    except Exception as e:
        logger.exception(f"Failed to create/load session '{session_name}' due to the following error:{e}")
        traceback.print_exc()

    runner = Runner(
    app=db_manager_app,
    session_service=session_service,
    )

    logger.info("Runner initialized successfully")

    while True:

        try:
            user_prompt = input("\nEnter your database request (or type 'exit' to quit): ").strip()
            if user_prompt.lower() == 'exit':
                logger.info("User requested exit, exiting the database management agent. Goodbye!")
                break
            logger.info(f"Received user request: {user_prompt}")
            await run_db_workflow(runner, user_prompt, session_id=session_name)

        except Exception as e:
            logger.exception(f"Unhandled error during workflow execution: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
