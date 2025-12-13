import asyncio
import os
import glob

from agents import db_manager_app
from memory_managment import compress_history_if_needed
from workflow import run_db_workflow

SESSION_DIR = "./sessions"

def get_session():
    """
    Retrieves an existing session ID or creates a new one based on user input.
    """
    if not os.path.exists(SESSION_DIR): os.makedirs(SESSION_DIR)
    existing_sessions = glob.glob(os.path.join(SESSION_DIR, "session_*.json"))
    sessions_ids = [os.path.splitext(os.path.basename(s))[0] for s in existing_sessions]

    print("Existing sessions:")
    for sid in sessions_ids:
        print(f"- {sid}")

    choice = input("Enter session ID to continue or press Enter to create a new session: ").strip()
    if choice and choice in sessions_ids:
        return choice
    return "default_session"
