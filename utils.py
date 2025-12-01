from google.adk.tools.tool_context import ToolContext

from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter
from typing import Dict, Any
import re

import logging

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Delete operation utility
# -----------------------------------------------------------------

def decide_and_perform_delete_records(db_path, table,  tool_context: ToolContext, filters=None, limit=None, dry_run=True):
    # First, perform a dry run to see how many records would be deleted
    dry_run_result = delete_records_by_filter(db_path, table, filters, limit, dry_run=True)
    potential_deletions = dry_run_result.get("delete_candidate", 0)
    logger.info(f"Dry run: {potential_deletions["preview_count"]} records would be deleted from {table}.")

    threshold_deletion = 10  # Define a threshold for maximum deletions allowed
    if potential_deletions <= threshold_deletion:
        real_result = delete_records_by_filter(db_path, table, filters, limit, dry_run=False)
        return {
            "status": "approved",
            "message": f"Proceeding with deletion of {potential_deletions} records from {table}.",
            "deleted_count": real_result,
        }

    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=f"Attempting to delete {potential_deletions} records from {table}. This exceeds the threshold of {threshold_deletion}. Do you want to proceed?",
            payload={"db_path": db_path, "table": table, "filters": filters, "limit": limit, "dry_run": False}
        )
        return {
            "status": "pending",
            "message": f"Deletion of {potential_deletions} records from {table} requires confirmation.",
        }
    
    if tool_context.tool_confirmation.confirmed:
        result = delete_records_by_filter(db_path, table, filters, limit, dry_run=False)
        return {
            "status": "approved",
            "message": f"Proceeding with deletion of {potential_deletions} records from {table}.",
            "deleted_count": result["deleted"],
        }
    
    else:
        return {
            "status": "denied",
            "message": f"Deletion of {potential_deletions} records from {table} has been cancelled by the user.",
        }

def ask_for_deletion_confirmation(tool_context: ToolContext, db_path:str, table:str, filters:Dict[str, Any], limit:int=10, dry_run:bool=True)->Dict[str, Any]:
    """
    pauses execution and asks for user confirmation for the deletion operation. 
    Completes or cancles based on the approval descision.



    """
    # initial confirmation request
    if not tool_context.tool_confirmation:
        dry_run_result = delete_records_by_filter(db_path, table, filters, limit, dry_run=True)
        logger.info(f"Dry run: {dry_run_result['preview_count']} records would be deleted from {table}. Check {dry_run_result['preview_path']} for preview.")
        tool_context.request_confirmation(hint=f"Attempting to delete {dry_run_result['preview_count']} records from {table}. Do you want to proceed?",
        payload={"db_path":db_path, "table": table,"filters":filters,"limit":limit, "dry_run":dry_run})

        return {
            "status": "pending",
            "message": f"Deletion of {dry_run_result['preview_count']} records from {table} requires confirmation.",
        }
    # user confirmed
    if tool_context.tool_confirmation.confirmed:
        result = delete_records_by_filter(db_path, table, filters, limit, dry_run=dry_run)
        return {
            "status": "approved",
            "message": f"Proceeding with deletion of {result['deleted']} records from {table}.",
            "deleted_count": result["deleted"],
            "deleted_records_preview_path": result.get("preview_path", "")
        }
    # user denied
    else:
        return {
            "status": "denied",
            "message": f"Deletion of records from {table} has been cancelled by the user.",
        }
    
    
from google.genai.errors import ClientError
from google.adk.runners import InMemoryRunner
import asyncio
import logging

# Backoff helper that honors RetryInfo on 429
# async def run_with_backoff(runner: InMemoryRunner, prompt: str):
#     while True:
#         try:
#             return await runner.run_debug(prompt)
#         except ClientError as e:
#             # Only handle 429; re-raise others
#             if getattr(e, "status_code", None) != 429:
#                 raise
#             # Default wait
#             delay = 65
#             try:
#                 details = (e.response_json or {}).get("error", {}).get("details", [])
#                 for d in details:
#                     if d.get("@type", "").endswith("RetryInfo"):
#                         retry = d.get("retryDelay", "60s").rstrip("s")
#                         delay = max(5, int(float(retry)) + 2)
#                         break
#             except Exception:
#                 pass
#             await asyncio.sleep(delay)

logger = logging.getLogger(__name__)

async def run_with_backoff(runner: InMemoryRunner, prompt: str = None, max_retries: int = 3, **kwargs):
    """
    Robust wrapper that:
    1. Trims history to prevent Input Token Limit errors.
    2. Catches 429 errors and sleeps.
    3. Accepts **kwargs to handle 'confirmation=True' logic.
    """
    
    # --- FEATURE 1: PREVENTATIVE TRIMMING ---
    # If history is getting huge (> 15 turns), keep only system prompt + last 10 turns.
    # This keeps you under the 250k token limit.
    if hasattr(runner, 'history') and len(runner.history) > 15:
        logger.info(f"History length {len(runner.history)} too high. Trimming...")
        # Keep index 0 (System Instruction) and the last 10 interactions
        runner.history = [runner.history[0]] + runner.history[-10:]

    attempt = 0
    while attempt < max_retries:
        try:
            # --- FEATURE 2: ARGUMENT FLEXIBILITY ---
            # We pass **kwargs so you can use this for confirmation=True later
            return await runner.run_debug(prompt, **kwargs)
            
        except ClientError as e:
            error_code = getattr(e, "code", None) or getattr(e, "status_code", None)
            
            if error_code == 429:
                attempt += 1
                wait_time = 65  # Safe buffer for 1-minute quota reset
                
                msg = f"[⚠️ QUOTA EXCEEDED] 429 Hit. Attempt {attempt}/{max_retries}. Sleeping {wait_time}s..."
                print(msg)
                logger.warning(msg)
                
                await asyncio.sleep(wait_time)
                continue 
            
            # Re-raise non-429 errors immediately
            raise e
            
    # If we run out of retries
    raise RuntimeError("Max retries exceeded for API rate limit.")