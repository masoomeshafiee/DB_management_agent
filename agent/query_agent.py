from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

import logging
from datetime import datetime
from typing import Optional

from lab_data_manager.queries import (
    list_experiments,
    list_experiments_between_dates,
    list_experiments_in_period,
    list_recent_experiments,
    find_most_recent_experiment,
    find_earliest_experiment,
    count_experiments_by_period,
    count_experiments_trend,
    count_entity_by_another,
    find_experiments_missing_files,
    find_duplicate_experiments,
    find_missing_values,
)

from .config import retry_config

logger = logging.getLogger(__name__)

# Resolve DB path relative to this file so it works regardless of working directory
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sample_data.db")

current_date = datetime.now().strftime("%B %d, %Y")

# ---------------------------------------------------------------------------
# Helper: convert a DataFrame result to a readable string for the agent
# ---------------------------------------------------------------------------

def _df_to_str(df, max_rows: int = 50) -> str:
    if df is None:
        return "No results found or a database error occurred."
    if df.empty:
        return "No records matched the given criteria."
    total = len(df)
    shown = df.head(max_rows)
    result = shown.to_string(index=False)
    if total > max_rows:
        result += f"\n\n... ({total - max_rows} more rows not shown. Use the limit parameter to retrieve more.)"
    else:
        result += f"\n\nTotal records: {total}"
    return result


# ---------------------------------------------------------------------------
# Tool functions (each wraps one library query)
# ---------------------------------------------------------------------------

def search_experiments(
    filters: dict,
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 20,
) -> str:
    """
    Search and list experiments using one or more filter criteria.

    Supported filter keys: organism, protein, strain, condition, user_name, email,
    comment, capture_setting_id, capture_type, replicate, experiment_id,
    raw_file_id, raw_file_name, tracking_file_id, mask_id, analysis_file_id,
    analysis_result_id, raw_file_type, mask_type, mask_file_type,
    analysis_file_type, analysis_result_type, is_valid,
    date (YYYYMMDD string), exposure_time (seconds), time_interval (seconds),
    concentration_unit (nM/uM/mM/M), concentration_value,
    dye_concentration_unit, dye_concentration_value.

    Args:
        filters: Dictionary of filter criteria. Pass {} for no filter (returns all).
        db_path: Path to the SQLite database file.
        limit: Maximum number of records to return.

    Returns:
        Formatted table of matching experiments.
    """
    logger.info("search_experiments | filters=%s limit=%s", filters, limit)
    df = list_experiments(db_path, filters=filters, limit=limit)
    return _df_to_str(df)


def search_experiments_by_date_range(
    start_date: str,
    end_date: str,
    filters: dict,
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 20,
) -> str:
    """
    List experiments conducted between two dates (inclusive).

    Args:
        start_date: Start date in YYYYMMDD format (e.g., "20230101").
        end_date:   End date in YYYYMMDD format (e.g., "20231231").
        filters:    Additional filter criteria (same keys as search_experiments).
        db_path:    Path to the SQLite database file.
        limit:      Maximum number of records to return.

    Returns:
        Formatted table of matching experiments ordered by date ascending.
    """
    logger.info("search_experiments_by_date_range | %s to %s filters=%s", start_date, end_date, filters)
    df = list_experiments_between_dates(db_path, start_date, end_date, filters=filters, limit=limit)
    return _df_to_str(df)


def search_experiments_in_period(
    filters: dict,
    db_path: str = _DEFAULT_DB_PATH,
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 20,
) -> str:
    """
    List experiments run in a specific year and/or month.

    Args:
        filters: Additional filter criteria.
        db_path: Path to the SQLite database file.
        year:    4-digit year (e.g., 2023). Omit for any year.
        month:   Month number 1-12 (e.g., 3 for March). Omit for any month.
        limit:   Maximum number of records to return.

    Returns:
        Formatted table of matching experiments.
    """
    logger.info("search_experiments_in_period | year=%s month=%s filters=%s", year, month, filters)
    df = list_experiments_in_period(db_path, year=year, month=month, filters=filters, limit=limit)
    return _df_to_str(df)


def search_recent_experiments(
    days: int = 30,
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 50,
) -> str:
    """
    List experiments from the last N days.

    Args:
        days:    How many days back to look (e.g., 30 for last month).
        filters: Additional filter criteria.
        db_path: Path to the SQLite database file.
        limit:   Maximum number of records to return.

    Returns:
        Formatted table of recent experiments ordered by date descending.
    """
    logger.info("search_recent_experiments | days=%s filters=%s", days, filters)
    df = list_recent_experiments(db_path, days=days, filters=filters, limit=limit)
    return _df_to_str(df)


def get_most_recent_experiment(
    filters: dict,
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Find the single most recent experiment matching the given filters.

    Args:
        filters: Filter criteria to narrow the search.
        db_path: Path to the SQLite database file.

    Returns:
        The most recent matching experiment's details.
    """
    logger.info("get_most_recent_experiment | filters=%s", filters)
    df = find_most_recent_experiment(db_path, filters=filters)
    return _df_to_str(df)


def get_earliest_experiment(
    filters: dict,
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Find the single earliest (oldest) experiment matching the given filters.

    Args:
        filters: Filter criteria to narrow the search.
        db_path: Path to the SQLite database file.

    Returns:
        The earliest matching experiment's details.
    """
    logger.info("get_earliest_experiment | filters=%s", filters)
    df = find_earliest_experiment(db_path, filters=filters)
    return _df_to_str(df)


def count_experiments_by_time_period(
    period: str = "year",
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Count experiments grouped by time period (year or month).

    Args:
        period:  "year" or "month".
        filters: Additional filter criteria.
        db_path: Path to the SQLite database file.

    Returns:
        Counts per period.
    """
    logger.info("count_experiments_by_time_period | period=%s filters=%s", period, filters)
    df = count_experiments_by_period(db_path, period=period, filters=filters)
    return _df_to_str(df)


def count_experiments_by_group(
    group_by: list[str],
    filters: dict = {},
    period: Optional[str] = None,
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Count experiments grouped by one or more entity columns, optionally also by time period.

    Args:
        group_by: List of column aliases to group by (e.g., ["protein"], ["organism", "condition"]).
                  Supported aliases: organism, protein, strain, condition, user_name,
                  capture_type, is_valid, date, replicate, etc.
        filters:  Additional filter criteria.
        period:   Optional time grouping: "year" or "month". Omit for no time grouping.
        db_path:  Path to the SQLite database file.

    Returns:
        Counts per group.
    """
    logger.info("count_experiments_by_group | group_by=%s period=%s filters=%s", group_by, period, filters)
    df = count_experiments_trend(db_path, period=period, group_by=group_by, filters=filters)
    return _df_to_str(df)


def count_one_entity_by_another(
    entity: str,
    by_entities: list[str],
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Count distinct values of one entity grouped by another.
    For example: "how many proteins per organism", "how many experiments per user".

    Args:
        entity:      The entity to count (e.g., "experiment_id", "protein", "*" for rows).
        by_entities: List of entities to group by (e.g., ["organism"], ["user_name", "protein"]).
        filters:     Additional filter criteria.
        db_path:     Path to the SQLite database file.

    Returns:
        Counts per group.
    """
    logger.info("count_one_entity_by_another | entity=%s by=%s filters=%s", entity, by_entities, filters)
    df = count_entity_by_another(db_path, entity=entity, by_entities=by_entities, filters=filters)
    return _df_to_str(df)


def find_experiments_with_missing_files(
    file_types: list[str] = ["raw", "tracking", "mask", "analysis"],
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 50,
) -> str:
    """
    Find experiments that are missing one or more expected associated file types.

    Args:
        file_types: Which file types to check. Options: "raw", "tracking", "mask", "analysis".
        filters:    Additional filter criteria.
        db_path:    Path to the SQLite database file.
        limit:      Maximum number of records to return.

    Returns:
        Table of experiments missing the specified file types.
    """
    logger.info("find_experiments_with_missing_files | file_types=%s filters=%s", file_types, filters)
    df = find_experiments_missing_files(db_path, file_types=file_types, filters=filters, limit=limit)
    return _df_to_str(df)


def find_duplicate_experiment_records(
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
) -> str:
    """
    Detect potential duplicate experiments — records that share the same key metadata
    (organism, protein, condition, date, replicate, capture_type, user) but have
    different IDs.

    Args:
        filters: Optional filters to narrow which experiments to check.
        db_path: Path to the SQLite database file.

    Returns:
        Groups of duplicate experiments with their shared IDs.
    """
    logger.info("find_duplicate_experiment_records | filters=%s", filters)
    df = find_duplicate_experiments(db_path, filters=filters)
    return _df_to_str(df)


def find_records_with_missing_values(
    requested_columns: list[str],
    missing_columns: list[str],
    main_table: str = "Experiment",
    mode: str = "any",
    filters: dict = {},
    db_path: str = _DEFAULT_DB_PATH,
    limit: int = 50,
) -> str:
    """
    Find records where specific columns are NULL or empty (data quality check).

    Args:
        requested_columns: Columns to display in results (use ["*"] for all columns in main_table).
        missing_columns:   Columns to check for missing values.
        main_table:        Table to search (default "Experiment"). Other options: "User", "Protein", etc.
        mode:              "any" = rows missing at least one column; "none" = entities with no values at all.
        filters:           Additional filter criteria.
        db_path:           Path to the SQLite database file.
        limit:             Maximum number of records to return.

    Returns:
        Records that have missing values in the specified columns.
    """
    logger.info("find_records_with_missing_values | missing=%s table=%s mode=%s", missing_columns, main_table, mode)
    df = find_missing_values(db_path, requested_columns, missing_columns, main_table=main_table, mode=mode, filters=filters, limit=limit)
    return _df_to_str(df)


# ---------------------------------------------------------------------------
# Query Agent
# ---------------------------------------------------------------------------

query_prompt = f"""
You are the Lab Data Query Agent. Your job is to answer user questions about the laboratory database by calling the right query tool.

# CURRENT DATE
Today is {current_date}. Use this to resolve relative dates like "last month", "this year", "yesterday".

# DATE FORMAT RULE
All dates must be converted to YYYYMMDD strings before passing them to tools.
- "March 2023" → start_date="20230301", end_date="20230331"
- "last year" → year=2024 (if today is 2025)
- "yesterday" → the actual date in YYYYMMDD format

# FILTER KEY RULES
When building a filters dict, only use these exact keys:
organism, protein, strain, condition, user_name, email, comment,
capture_setting_id, capture_type, replicate, experiment_id,
raw_file_id, raw_file_name, tracking_file_id, mask_id, analysis_file_id,
analysis_result_id, raw_file_type, mask_type, mask_file_type,
analysis_file_type, analysis_result_type, is_valid,
date (YYYYMMDD), exposure_time (float, seconds), time_interval (float, seconds),
concentration_unit (nM/uM/mM/M), concentration_value (float),
dye_concentration_unit, dye_concentration_value (float).

Do NOT use synonyms or variations. Do NOT include keys that the user did not mention.

# TOOL SELECTION GUIDE
- "show/list/find experiments [with criteria]" → search_experiments
- "experiments between [date] and [date]" → search_experiments_by_date_range
- "experiments in [month/year]" → search_experiments_in_period
- "experiments in the last N days/weeks" → search_recent_experiments
- "most recent experiment" → get_most_recent_experiment
- "earliest/first experiment" → get_earliest_experiment
- "how many experiments per year/month" → count_experiments_by_time_period
- "how many experiments per [protein/organism/user/...]" → count_experiments_by_group
- "how many [proteins/users/...] per [organism/...]" → count_one_entity_by_another
- "experiments missing [file type] files" → find_experiments_with_missing_files
- "duplicate experiments" → find_duplicate_experiment_records
- "experiments with missing [column]" or "incomplete data" → find_records_with_missing_values

# OUTPUT RULES
- After calling a tool, present the results clearly and concisely to the user.
- If the result is empty, say so and suggest the user refine their query.
- If you are unsure which tool to use, pick the closest match and explain your interpretation.
- Never invent data. Only report what the tools return.
"""

try:
    query_agent = Agent(
        name="query_agent",
        model=Gemini(model="gemini-2.5-flash-lite", api_key=os.getenv("GOOGLE_API_KEY"), retry_config=retry_config),
        description="Answers natural language questions about lab data by querying the database. Handles search, filtering, counting, trend analysis, and data quality checks.",
        instruction=query_prompt,
        tools=[
            search_experiments,
            search_experiments_by_date_range,
            search_experiments_in_period,
            search_recent_experiments,
            get_most_recent_experiment,
            get_earliest_experiment,
            count_experiments_by_time_period,
            count_experiments_by_group,
            count_one_entity_by_another,
            find_experiments_with_missing_files,
            find_duplicate_experiment_records,
            find_records_with_missing_values,
        ],
        output_key="query_result",
    )
    logger.info("Created agent: %s", query_agent.name)
except Exception as e:
    logger.exception("Error creating query_agent: %s", e)
    raise e
