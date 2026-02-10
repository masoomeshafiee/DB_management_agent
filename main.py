import asyncio
import os
import glob

from agent import utils
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService

from agent.agents import db_manager_app
from workflow import run_db_workflow

# Define where the database file will live
DB_FOLDER = "db_manager_app_state"
DB_FILE = "sessions.db"

def get_session_name():

    """Ask the user to provide a session name"""

    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    print(f"The sessions are stored in the: {DB_FOLDER}/{DB_FILE} file.")

    choice = input("Enter a session name to load or create (leave empty for default session): ").strip()

    return choice if choice else "default"


async def main():


    db_path = os.path.join(DB_FOLDER, DB_FILE)
    db_url = f"sqlite:///{db_path}"

    session_service = DatabaseSessionService(db_url)
    session_name = get_session_name()
    print(f"Using session name: {session_name}")

    try:
 
        await session_service.create_session(
            app_name=db_manager_app.name,
            user_id="default_user",
            session_id=session_name
        )
        print(f"Session '{session_name}' created successfully.")
    except Exception as e:
        print(f"Session '{session_name}' already exists. Loading existing session.")

    runner = Runner(
    app=db_manager_app,
    session_service=session_service,
    )

    while True:

        try:
            user_prompt = input("\nEnter your database request (or type 'exit' to quit): ").strip()
            if user_prompt.lower() == 'exit':
                print("Exiting the database management agent. Goodbye!")
                break

            await run_db_workflow(runner, user_prompt, session_id=session_name)

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
