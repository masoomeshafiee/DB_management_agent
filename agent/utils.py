from __future__ import annotations

from google.adk.tools.tool_context import ToolContext
from google.genai.errors import ClientError
from google.adk.runners import InMemoryRunner


from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter

import re
import logging
import asyncio
from typing import Any, Dict, Optional



logger = logging.getLogger(__name__) # for normal module logs
#audit_logger = logging.getLogger("db_management_agent.audit") # for “who did what” actions (these go to audit.log)


# -----------------------------------------------------------------
# Delete operation utility
# -----------------------------------------------------------------

# Not used:
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
        logger.info(f"Requesting user confirmation for deletion of {potential_deletions} records from {table}.")
        return {
            "status": "pending",
            "message": f"Deletion of {potential_deletions} records from {table} requires confirmation.",
        }
    
    if tool_context.tool_confirmation.confirmed:
        logger.info(f"User confirmed deletion of {potential_deletions} records from {table}. Proceeding with deletion.")
        result = delete_records_by_filter(db_path, table, filters, limit, dry_run=False)
        return {
            "status": "approved",
            "message": f"Proceeding with deletion of {potential_deletions} records from {table}.",
            "deleted_count": result["deleted"],
        }
    
    else:
        logger.info(f"User denied deletion of {potential_deletions} records from {table}. Cancelling deletion.")
        return {
            "status": "denied",
            "message": f"Deletion of {potential_deletions} records from {table} has been cancelled by the user.",
        }


def ask_for_deletion_confirmation(tool_context: ToolContext, db_path: str, table: str, filters: dict, limit: int | None = None, dry_run: bool = True) -> Dict[str, Any]:
    """
    pauses execution and asks for user confirmation for the deletion operation. 
    Completes or cancles based on the approval descision.

    """
    logger.info(f"AUDIT: User {tool_context.user_id} requested deletion on table {table} with filters {filters}.")

    # audit_logger.info(
    #     "Deletion requested | user_id=%s table=%s filters=%s limit=%s",
    #     getattr(tool_context, "user_id", None),
    #     table,
    #     filters,
    #     limit,
    # )
    

    # initial confirmation request
    if not tool_context.tool_confirmation:
        logger.info(f"Requesting confirmation from user {tool_context.user_id} for deletion on table {table} with filters {filters}.")
        dry_run_result = delete_records_by_filter(db_path, table, filters, limit, dry_run=True)

        #preview_count = int(dry_run_result.get("preview_count", 0))
        logger.info(
            "Delete dry-run | table=%s limit=%s",
            table,
            limit,
        )

        tool_context.request_confirmation(hint=f"Attempting to delete {dry_run_result['preview_count']} records from {table}. Do you want to proceed?",
        payload={"db_path":db_path, "table": table,"filters":filters,"limit":limit, "dry_run":dry_run})

        # audit_logger.info(
        #     "Deletion confirmation requested | user_id=%s table=%s",
        #     getattr(tool_context, "user_id", None),
        #     table,
            
        # )

        return {
            "status": "pending",
            "message": f"Deletion of {dry_run_result['preview_count']} records from {table} requires confirmation.",
            
        }
    # user confirmed
    if tool_context.tool_confirmation.confirmed:

        # audit_logger.info(
        #     "Deletion confirmed | user_id=%s table=%s filters=%s",
        #     getattr(tool_context, "user_id", None),
        #     table,
        #     filters,
        # )

        logger.info(f"User {tool_context.user_id} confirmed deletion on table {table} with filters {filters}. Proceeding with deletion.")
        result = delete_records_by_filter(db_path, table, filters, limit, dry_run=dry_run)
        #deleted_count = int(result.get("deleted", 0))
        #preview_path = result.get("preview_path", "")

        logger.info(
            "Deletion executed | table=%s",
            table,
        )
        # audit_logger.info(
        #     "Deletion executed | user_id=%s table=%s",
        #     getattr(tool_context, "user_id", None),
        #     table
            
        # )
        return {
            "status": "approved",
            "message": f"Proceeding with deletion of {result['deleted']} records from {table}.",
            "deleted_count": result["deleted"],
            "deleted_records_preview_path": result.get("preview_path", "")
        }
    # user denied

    
    else:
        # audit_logger.info(
        # "Deletion denied | user_id=%s table=%s filters=%s",
        # getattr(tool_context, "user_id", None),
        # table,
        # filters,)
        logger.info("Deletion cancelled by user | table=%s", table)
        return {
            "status": "denied",
            "message": f"Deletion of records from {table} has been cancelled by the user.",
        }
    

# -----------------------------------------------------------------
# This is a robust wrapper to run agents with backoff and history trimming
# -----------------------------------------------------------------
#it can be called instead of runner.async.run 
#This fuction was created to handle rate limit errors (429) and history trimming to avoid Input Token Limit errors.


async def run_with_backoff(runner: InMemoryRunner, prompt: str = None, max_retries: int = 3, session_id: str = "default_session", user_id: str = "default_user", **kwargs):
    """
    Robust wrapper for tunner.run_async that:
    1. Catches 429 errors and sleeps.
    2. Yields events like a normal runner.run_async call.
    """
    
    attempt = 0
    while attempt < max_retries:
        try:
            #The streaming is warpped and if the runner crashes due to 429, the exception is caught here.
            #now the runner has logging plugin, plugin callbacks will run as part of the runner lifecycle (before/after run, agent, tool, etc.) so we get to see everythin.

            # logger.info(
            #     "Runner call | attempt=%s/%s session_id=%s user_id=%s",
            #     attempt,
            #     max_retries,
            #     session_id,
            #     user_id,
            # )

            async for event in runner.run_async(
                user_id=user_id,
                new_message=prompt,
                session_id=session_id,
                **kwargs
            ):
                yield event

            logger.info("Runner completed successfully | session_id=%s", session_id)
            return  # If completed successfully, exit the function
            #return await runner.run_debug(prompt, **kwargs)
            
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
            logger.exception(f"ClientError in runner execution: {e}")
            raise e
            
    # If we run out of retries
    logger.error(f"Max retries exceeded for API rate limit after {max_retries} attempts.")
    raise RuntimeError("Max retries exceeded for API rate limit.")