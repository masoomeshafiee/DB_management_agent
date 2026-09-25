from __future__ import annotations

from google.adk.tools.tool_context import ToolContext
from google.genai.errors import ClientError
from google.adk.runners import InMemoryRunner


from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter

from .pydantic_models import ALLOWED_TABLES, StrictLabFilters, TABLE_ALIASES

import csv
import os
import re
import logging
import asyncio
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

# Resolved relative to this file (not the process cwd) so it works regardless
# of where the app is launched from — same approach query_agent.py uses for
# its own _DEFAULT_DB_PATH.
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_data.db")


# ADK State is mapping-like but does not implement dict.pop(). Assigning None
# records a state delta and makes subsequent pending-deletion checks evaluate
# as empty.
def clear_pending_deletion(tool_context: ToolContext) -> None:
    tool_context.state["pending_deletion"] = None


# -----------------------------------------------------------------
# Table name normalisation (replaces DeletionSchema.map_table_names)
# -----------------------------------------------------------------

def resolve_table_name(table: str) -> str:
    """Map natural language aliases to canonical table names.

    For example, "track" maps to "TrackingFiles" and "raw files" maps to
    "RawFiles".
    Returns the input unchanged if no alias matches.
    """
    name = table.strip().lower()
    for alias, canonical in TABLE_ALIASES.items():
        if re.search(rf'\b{alias}\b', name):
            return canonical
    return table


def validate_filters(filters: dict) -> tuple[dict, Optional[str]]:
    """Validate/normalize query filters through StrictLabFilters.

    query_agent's tools take a raw `filters: dict` straight from the LLM with
    no validation, unlike preview_deletion. This applies the same boundary
    check (rejects unknown filter keys, normalizes is_valid True/False/"yes"/
    "no" into the "Y"/"N" the database actually stores) so search filtering
    doesn't silently return zero rows the way deletion did before this fix.

    Returns (clean_filters, None) on success, or ({}, error_message) if the
    filters are invalid — callers should return the error message as-is.
    """
    try:
        validated = StrictLabFilters(**(filters or {}))
    except Exception as e:
        return {}, f"Invalid filter fields: {e}"
    return validated.model_dump(exclude_none=True), None


# -----------------------------------------------------------------
# Delete operation utilities
# -----------------------------------------------------------------

# Matches phrasing that explicitly asks for a capped number of records, e.g.
# "delete 5 records", "remove the first 3 rows", "top 10 entries".
_EXPLICIT_LIMIT_PATTERN = re.compile(
    r"\b\d+\s*(records?|rows?|entries|items|files)\b"
    r"|\b(first|top)\s+\d+\b"
    r"|\blimit(ed)?\s+to\s+\d+\b",
    re.IGNORECASE,
)


def _get_raw_user_text(tool_context: ToolContext) -> str:
    """Best-effort read of the user's own words for this turn, bypassing
    whatever the filter-extraction LLM decided to pass along."""
    try:
        user_content = tool_context._invocation_context.user_content
        if user_content and user_content.parts:
            return " ".join(p.text for p in user_content.parts if getattr(p, "text", None))
    except Exception:
        logger.debug("Could not read raw user text from invocation context", exc_info=True)
    return ""


def _sanitize_limit(tool_context: ToolContext, limit: int | None) -> int | None:
    """Deterministically drop any limit the extraction LLM invented unless the
    user's own request explicitly asked for a specific count. LLMs are prone
    to hallucinating a plausible-looking default (e.g. 10) even when told not
    to, which would silently turn "delete all matching records" into "delete
    only the first N" — this makes that decision code, not model judgment."""
    if limit is None:
        return None
    raw_text = _get_raw_user_text(tool_context)
    if _EXPLICIT_LIMIT_PATTERN.search(raw_text):
        return limit
    logger.warning(
        "Ignoring model-provided limit=%s — user request did not explicitly ask for a count: %r",
        limit,
        raw_text,
    )
    return None


def preview_deletion(tool_context: ToolContext, db_path: str, table: str, filters: dict, limit: int | None = None) -> Dict[str, Any]:
    """
    Validates filters, performs a dry-run, and stores the pending operation in
    session state. Does NOT delete anything.
    """
    # --- Resolve table alias ("track" → "TrackingFiles") ---
    table = resolve_table_name(table)
    limit = _sanitize_limit(tool_context, limit)

    # --- Safety checks ---
    if not table:
        logger.warning("preview_deletion blocked: no table specified")
        return {"status": "blocked", "message": "No table specified. Please provide a table name."}
    if not filters:
        logger.warning("preview_deletion blocked: empty filters for table=%s", table)
        return {
            "status": "blocked",
            "message": (
                f"No filter criteria provided. Deleting without filters would remove "
                f"ALL records from '{table}'. Please specify criteria (e.g. date, organism, is_valid)."
            ),
        }
    if table not in ALLOWED_TABLES:
        logger.warning("preview_deletion blocked: unsupported table=%s", table)
        return {
            "status": "blocked",
            "message": f"Unsupported table name: '{table}'.",
        }

    # Validate again at the database boundary and reject unsupported fields.
    try:
        validated = StrictLabFilters(**filters)
        clean_filters = validated.model_dump(exclude_none=True)
    except Exception as e:
        logger.warning("preview_deletion blocked: invalid filters | %s", e)
        return {
            "status": "blocked",
            "message": f"Invalid filter fields: {e}",
        }

    logger.info("preview_deletion | table=%s filters=%s", table, clean_filters)
    try:
        result = delete_records_by_filter(
            db_path,
            table,
            clean_filters,
            limit,
            dry_run=True,
        )
    except Exception as e:
        clear_pending_deletion(tool_context)
        logger.exception(
            "preview_deletion failed | table=%s filters=%s",
            table,
            clean_filters,
        )
        return {
            "status": "error",
            "message": f"Deletion preview failed: {e}",
        }

    preview_count = result.get("preview_count", 0)
    preview_path = result.get("preview_path")
    if preview_count <= 0:
        clear_pending_deletion(tool_context)
        return {
            "status": "no_matches",
            "preview_count": 0,
            "message": "No records matched the deletion criteria.",
        }

    # Store pending deletion so execute_deletion can read it on the next turn
    tool_context.state["pending_deletion"] = {
        "db_path": db_path,
        "table": table,
        "filters": clean_filters,
        "limit": limit,
        "preview_count": preview_count,
        "preview_path": preview_path,
    }
    logger.info("preview_deletion stored in state | count=%s", preview_count)
    return {
        "status": "preview",
        "preview_count": preview_count,
        "preview_path": preview_path,
        "message": (
            f"{preview_count} record(s) from '{table}' would be deleted.\n"
            f"Filters applied: {clean_filters}\n"
            f"Preview saved to: {preview_path}\n"
            "Review the platform confirmation request to approve or reject deletion."
        ),
    }


def execute_deletion(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Handles the confirmed or rejected deletion that was previewed previously.
    Reads db_path, table, filters, and limit from session state key
    'pending_deletion'. This tool must be registered with confirmation required.
    Pending state is cleared after approval, rejection, or execution failure.
    """
    pending = tool_context.state.get("pending_deletion")
    if not pending:
        logger.warning("execute_deletion called but no pending_deletion in state")
        return {
            "status": "error",
            "message": "No pending deletion found. Please submit a new delete request.",
        }

    confirmation = getattr(tool_context, "tool_confirmation", None)
    if confirmation is None:
        logger.error("execute_deletion called without confirmation context")
        clear_pending_deletion(tool_context)
        return {
            "status": "error",
            "message": "Deletion was not executed because confirmation was unavailable.",
        }

    if not confirmation.confirmed:
        clear_pending_deletion(tool_context)
        logger.info("execute_deletion denied | table=%s", pending["table"])
        return {
            "status": "cancelled",
            "message": "Deletion cancelled. No records were removed.",
        }

    db_path = pending["db_path"]
    table   = pending["table"]
    filters = pending["filters"]
    limit   = pending.get("limit")

    # The request has reached a terminal approved state. Remove it before
    # execution so a database failure cannot leave an old deletion pending.
    clear_pending_deletion(tool_context)

    logger.info("execute_deletion | table=%s filters=%s", table, filters)
    try:
        result = delete_records_by_filter(
            db_path,
            table,
            filters,
            limit,
            dry_run=False,
        )
    except Exception as e:
        logger.exception(
            "execute_deletion failed | table=%s filters=%s",
            table,
            filters,
        )
        return {
            "status": "error",
            "message": (
                f"Deletion failed before any records were removed: {e}."
            ),
        }

    if not isinstance(result, dict):
        logger.error(
            "execute_deletion received unexpected result type: %s",
            type(result).__name__,
        )
        return {
            "status": "error",
            "message": "Deletion returned an unexpected result.",
        }

    logger.info("execute_deletion complete | deleted=%s", result.get("deleted"))
    return {
        "status": "completed",
        "deleted_count": result.get("deleted", 0),
        "message": f"Successfully deleted {result.get('deleted', 0)} record(s) from '{table}'.",
    }


# -----------------------------------------------------------------
# Insert operation utilities
# -----------------------------------------------------------------

def _count_data_rows(csv_path: str) -> int:
    """Count non-empty data rows in a CSV, mirroring the "skip empty rows"
    check insert_from_csv does internally, so the reported total lines up
    with what it actually tried to process."""
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            return sum(1 for row in reader if any(row.values()))
    except OSError:
        logger.warning("Could not read %s to count rows for reporting", csv_path, exc_info=True)
        return 0


def insert_csv_with_report(
    tool_context: ToolContext, csv_path: str, db_path: str = _DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Wraps insert_from_csv, storing {inserted_count, skipped_count,
    skipped_rows} in session state (like preview_deletion does with its
    preview) so the UI can render a table instead of trusting the model's
    prose. db_path defaults to data/sample_data.db so a request that omits
    it still works. See DESIGN_LOG.md 3.7 for why: the model was previously
    hallucinating db_path=csv_path, which crashed sqlite3 with an unhandled
    500 further down.
    """
    if not csv_path or not db_path:
        return {
            "status": "error",
            "message": "Both a CSV file path and a database file path are required. "
            "Please ask the user for whichever one is missing.",
        }
    if os.path.abspath(csv_path) == os.path.abspath(db_path):
        logger.warning(
            "insert_csv_with_report blocked: csv_path and db_path are the same file (%s)",
            csv_path,
        )
        return {
            "status": "error",
            "message": (
                f"'{csv_path}' was given as both the CSV file and the database file. "
                "These must be different — please ask the user for the actual database "
                "file path (e.g. data/sample_data.db)."
            ),
        }
    if not os.path.isfile(csv_path):
        return {"status": "error", "message": f"CSV file not found: '{csv_path}'."}
    if not os.path.isfile(db_path):
        return {
            "status": "error",
            "message": (
                f"Database file not found: '{db_path}'. Please ask the user to confirm "
                "the correct database path."
            ),
        }

    skipped_rows: list[Dict[str, Any]] = []
    try:
        skipped_rows = insert_from_csv(csv_path, db_path, skipped_rows)
    except Exception as e:
        logger.exception("insert_csv_with_report failed | csv_path=%s db_path=%s", csv_path, db_path)
        return {"status": "error", "message": f"Insertion failed: {e}"}

    total_rows = _count_data_rows(csv_path)
    skipped_count = len(skipped_rows)
    inserted_count = max(total_rows - skipped_count, 0)

    tool_context.state["last_insert_result"] = {
        "csv_path": csv_path,
        "db_path": db_path,
        "total_rows": total_rows,
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "skipped_rows": skipped_rows,
    }

    logger.info(
        "insert_csv_with_report | csv_path=%s inserted=%s skipped=%s",
        csv_path,
        inserted_count,
        skipped_count,
    )
    return {
        "status": "completed",
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "message": (
            f"Inserted {inserted_count} record(s) from '{csv_path}'. "
            f"{skipped_count} row(s) were skipped."
        ),
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
