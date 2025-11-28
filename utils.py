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
    


from google.genai.errors import ClientError
rom google.adk.runners import InMemoryRunner
import asyncio
# Backoff helper that honors RetryInfo on 429
async def run_with_backoff(runner: InMemoryRunner, prompt: str):
    while True:
        try:
            return await runner.run_debug(prompt)
        except ClientError as e:
            # Only handle 429; re-raise others
            if getattr(e, "status_code", None) != 429:
                raise
            # Default wait
            delay = 65
            try:
                details = (e.response_json or {}).get("error", {}).get("details", [])
                for d in details:
                    if d.get("@type", "").endswith("RetryInfo"):
                        retry = d.get("retryDelay", "60s").rstrip("s")
                        delay = max(5, int(float(retry)) + 2)
                        break
            except Exception:
                pass
            await asyncio.sleep(delay)