"""Evaluation scenarios, written once and turned into ADK eval sets.

Most cases come from the hand-written scenarios in test/scenarios/ (the
`# from ...` comments say which). Where those notes no longer match the app
they are corrected here, for example:

- The filter agent cannot return `{error: ...}`: its output is forced into
  DeletionSchema, and an unusable request gets *empty filters* so the code in
  preview_deletion blocks it. Those cases expect outcome "blocked".
- Table names are the real ones (`RawFiles`, `CaptureSetting`), and the
  example database paths are dropped because those files do not exist.

Expected counts were checked against data/sample_data.db (the evaluation runs
on a copy of it, see sandbox.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from google.adk.evaluation.eval_case import EvalCase, IntermediateData, Invocation
from google.adk.evaluation.eval_set import EvalSet
from google.genai import types

from .metrics import AWAITING_APPROVAL, BLOCKED, NO_MATCHES

INSERT_FIXTURES = "test/scenarios/insertion"
# Where the validation agent is told to write invalid rows during the eval.
INVALID_ROWS_PATH = "evaluation/.work/invalid_rows.csv"

QUERY = "query_agent"
DELETE = "delete_supervisor_agent"
INSERT = "insert_supervisor_agent"


@dataclass
class Scenario:
    """One user request and what should happen.

    Only the fields a suite's metrics read need to be set.
    """

    id: str
    request: str
    route: Optional[str] = None          # agent the root should transfer to (None: no transfer)
    table: Optional[str] = None          # expected deletion target
    filters: Optional[dict] = None       # expected deletion filters
    limit: Optional[int] = None          # expected deletion limit
    outcome: Optional[str] = None        # expected deletion outcome
    tools: tuple = ()                    # expected tool calls: (name, {args subset}), in order
    mentions: tuple = ()                 # phrases the final answer must contain
    source: str = ""                     # where the case came from


def _call(name: str, args: Optional[dict] = None) -> types.FunctionCall:
    return types.FunctionCall(name=name, args=args or {})


def to_eval_case(scenario: Scenario, include_route: bool = True) -> EvalCase:
    """Encode a scenario as an ADK EvalCase: expected tool calls, tool responses and final answer."""
    calls: list[types.FunctionCall] = []
    responses: list[types.FunctionResponse] = []

    if include_route and scenario.route:
        calls.append(_call("transfer_to_agent", {"agent_name": scenario.route}))

    if scenario.table is not None or scenario.filters is not None:
        calls.append(_call("preview_deletion", {
            "table": scenario.table,
            "filters": scenario.filters or {},
            "limit": scenario.limit,
        }))
        if scenario.outcome == AWAITING_APPROVAL:
            responses.append(types.FunctionResponse(name="preview_deletion", response={"status": "preview"}))
            calls.append(_call("execute_deletion"))
        elif scenario.outcome == NO_MATCHES:
            responses.append(types.FunctionResponse(name="preview_deletion", response={"status": "no_matches"}))
        elif scenario.outcome == BLOCKED:
            responses.append(types.FunctionResponse(name="preview_deletion", response={"status": "blocked"}))

    calls.extend(_call(name, args) for name, args in scenario.tools)

    final = None
    if scenario.mentions:
        final = types.Content(role="model", parts=[types.Part(text="\n".join(scenario.mentions))])

    return EvalCase(
        eval_id=scenario.id,
        conversation=[
            Invocation(
                invocation_id=f"{scenario.id}-1",
                user_content=types.Content(role="user", parts=[types.Part(text=scenario.request)]),
                final_response=final,
                intermediate_data=IntermediateData(tool_uses=calls, tool_responses=responses),
            )
        ],
    )


def to_eval_set(eval_set_id: str, description: str, scenarios: list[Scenario], include_route: bool = True) -> EvalSet:
    return EvalSet(
        eval_set_id=eval_set_id,
        name=eval_set_id,
        description=description,
        eval_cases=[to_eval_case(s, include_route) for s in scenarios],
    )


# ---------------------------------------------------------------------------
# Routing: does the root agent pick the right specialist?
# ---------------------------------------------------------------------------

ROUTING = [
    # Search, phrased the many ways biologists ask.
    Scenario("route-find-yeast", "Find all records for organism yeast", route=QUERY, source="filter_test.py #1"),
    Scenario("route-list-invalid", "Show me the experiments that are marked invalid", route=QUERY),
    Scenario("route-count-by-organism", "How many experiments do we have per organism?", route=QUERY),
    Scenario("route-most-recent", "What was our most recent experiment?", route=QUERY),
    Scenario("route-missing-files", "Which experiments are missing tracking files?", route=QUERY),
    Scenario("route-duplicates", "Are there any duplicate experiment records?", route=QUERY),
    Scenario("route-period", "List the experiments we ran in August 2023", route=QUERY),
    Scenario("route-question-with-delete-word", "How many records would be affected if I deleted the invalid experiments?",
             route=QUERY),
    # Delete, including indirect verbs.
    Scenario("route-delete-invalid", "Delete all experiments that are marked as invalid", route=DELETE, source="delete_test.py #2"),
    Scenario("route-remove", "Remove the tracking files from August 3rd, 2023", route=DELETE, source="delete_test.py #3"),
    Scenario("route-get-rid", "Get rid of the masks for untreated Rfa1 experiments that are invalid", route=DELETE,
             source="delete_test.py #5"),
    Scenario("route-clean-up", "Clean up the database by deleting invalid raw files", route=DELETE),
    Scenario("route-delete-everything", "Delete all records from the User table", route=DELETE, source="delete_test.py #7"),
    Scenario("route-delete-limit", "Delete 2 invalid raw files", route=DELETE),
    # Insert.
    Scenario("route-insert", f"Insert the rows from {INSERT_FIXTURES}/valid.csv", route=INSERT, source="insert_test.py insertion #1"),
    Scenario("route-upload", f"Upload {INSERT_FIXTURES}/rows_with_foreign_keys.csv to the database", route=INSERT),
    Scenario("route-add", f"Please add the new metadata in {INSERT_FIXTURES}/valid_rows_non_existing_db.csv", route=INSERT),
    Scenario("route-validate", f"Validate and insert the CSV file {INSERT_FIXTURES}/mixed_valid_invalid.csv",
             route=INSERT, source="insert_test.py validation #5"),
    # Not a database operation: nothing should be routed.
    Scenario("route-greeting", "Hi there!", route=None),
    Scenario("route-off-topic", "Where does this database belong to?", route=None, source="filter_test.py #6"),
    Scenario("route-general-question", "What is a fluorescence microscope?", route=None),
]


# ---------------------------------------------------------------------------
# Filter extraction: the filter agent on its own (one model call per case)
# ---------------------------------------------------------------------------

FILTER_EXTRACTION = [
    Scenario("filter-single", "Delete all experiments for organism yeast",
             table="Experiment", filters={"organism": "yeast"}, source="filter_test.py #1"),
    Scenario("filter-multiple", "Delete all experiment records for organism E.coli and protein DnaA",
             table="Experiment", filters={"organism": "E.coli", "protein": "DnaA"}, source="filter_test.py #2"),
    Scenario("filter-date", "Delete all experiment records from 2023-08-03",
             table="Experiment", filters={"date": "20230803"}, source="filter_test.py #7"),
    Scenario("filter-date-words", "Remove the tracking files from August 3rd, 2023",
             table="TrackingFiles", filters={"date": "20230803"}, source="delete_test.py #3"),
    Scenario("filter-exposure-seconds", "Delete all capture settings with exposure time 2.5 seconds",
             table="CaptureSetting", filters={"exposure_time": 2.5}, source="filter_test.py #8"),
    Scenario("filter-exposure-ms", "Delete capture settings with an exposure time of 500 milliseconds",
             table="CaptureSetting", filters={"exposure_time": 0.5}),
    Scenario("filter-time-minutes", "Delete experiments with a time interval of 5 minutes",
             table="Experiment", filters={"time_interval": 300.0}, source="filter_test.py #10 (minutes → seconds)"),
    Scenario("filter-concentration-unit", "Delete experiments with concentration unit nM",
             table="Experiment", filters={"concentration_unit": "nM"}, source="filter_test.py #9"),
    Scenario("filter-is-valid", "Delete all experiment records that are not valid",
             table="Experiment", filters={"is_valid": False}, source="filter_test.py #11"),
    Scenario("filter-four-keys", "Delete all yeast Rfa1 raw files that are untreated and marked as invalid",
             table="RawFiles", filters={"organism": "yeast", "protein": "Rfa1", "condition": "untreated", "is_valid": False},
             source="delete_test.py #3"),
    Scenario("filter-alias-table", "Delete the tracks recorded on 2023-08-03",
             table="TrackingFiles", filters={"date": "20230803"}),
    Scenario("filter-explicit-limit", "Delete 5 records from TrackingFiles where organism is yeast",
             table="TrackingFiles", filters={"organism": "yeast"}, limit=5),
    Scenario("filter-all-is-not-a-limit", "Delete all invalid masks",
             table="Masks", filters={"is_valid": False}, limit=None),
    Scenario("filter-no-criteria", "Delete all records from the User table",
             table="User", filters={}, source="delete_test.py #7 (must stay empty)"),
    Scenario("filter-delete-everything", "Delete everything in the experiments table",
             table="Experiment", filters={}),
]


# ---------------------------------------------------------------------------
# Deletion, end to end through the root agent (on a copy of the database)
# ---------------------------------------------------------------------------

DELETION = [
    # Valid requests: should stop at the approval step, never execute.
    Scenario("delete-invalid-experiments", "Delete all experiments that are marked as invalid",
             route=DELETE, table="Experiment", filters={"is_valid": False}, outcome=AWAITING_APPROVAL,
             source="delete_test.py #2 (14 rows)"),
    Scenario("delete-by-date", "Delete all experiments that took place on August 3rd, 2023",
             route=DELETE, table="Experiment", filters={"date": "20230803"}, outcome=AWAITING_APPROVAL,
             source="delete_test.py #2 (1 row)"),
    Scenario("delete-fk-tracking", "Delete all records from table TrackingFiles from August 3rd, 2023",
             route=DELETE, table="TrackingFiles", filters={"date": "20230803"}, outcome=AWAITING_APPROVAL,
             source="delete_test.py #3 (18 rows)"),
    Scenario("delete-fk-four-filters", "Delete all yeast Rfa1 raw files that are untreated and marked as invalid",
             route=DELETE, table="RawFiles",
             filters={"organism": "yeast", "protein": "Rfa1", "condition": "untreated", "is_valid": False},
             outcome=AWAITING_APPROVAL, source="delete_test.py #3 (625 rows)"),
    Scenario("delete-multi-fk-masks", "Delete all masks for invalid experiments for Rfa1 protein that are untreated",
             route=DELETE, table="Masks", filters={"protein": "Rfa1", "condition": "untreated", "is_valid": False},
             outcome=AWAITING_APPROVAL, source="delete_test.py #5 (26 rows)"),
    Scenario("delete-with-limit", "Delete 2 records of invalid raw files",
             route=DELETE, table="RawFiles", filters={"is_valid": False}, limit=2, outcome=AWAITING_APPROVAL),
    # Valid requests that match nothing.
    Scenario("delete-no-match-capture-type", "Delete all time-lapse capture settings",
             route=DELETE, table="CaptureSetting", filters={"capture_type": "time_lapse"}, outcome=NO_MATCHES,
             source="delete_test.py #4"),
    Scenario("delete-no-match-exposure", "Delete all capture settings with exposure time of 1000 seconds",
             route=DELETE, table="CaptureSetting", filters={"exposure_time": 1000.0}, outcome=NO_MATCHES,
             source="delete_test.py #8"),
    Scenario("delete-no-match-organism", "Delete all experiments for organism E.coli and protein DnaA",
             route=DELETE, table="Experiment", filters={"organism": "E.coli", "protein": "DnaA"}, outcome=NO_MATCHES,
             source="filter_test.py #2"),
    # Unsafe or unusable requests: must be blocked before any approval request.
    Scenario("delete-no-filters", "Delete all records from the User table",
             route=DELETE, table="User", filters={}, outcome=BLOCKED, source="delete_test.py #7"),
    Scenario("delete-everything", "Delete everything",
             route=DELETE, table=None, filters={}, outcome=BLOCKED),
    Scenario("delete-unknown-table", "Delete all records from the ImageStacks table where organism is yeast and protein is Rfa1",
             route=DELETE, table="ImageStacks", filters={"organism": "yeast", "protein": "Rfa1"}, outcome=BLOCKED,
             source="delete_test.py #6"),
    Scenario("delete-unsupported-field", "Delete all experiments for organism yeast and location lab1",
             route=DELETE, table="Experiment", filters={"organism": "yeast", "location": "lab1"}, outcome=BLOCKED,
             source="filter_test.py #3"),
]


# ---------------------------------------------------------------------------
# Search: the query agent on its own
# ---------------------------------------------------------------------------

SEARCH = [
    Scenario("search-invalid", "Find all experiment records that are not valid",
             tools=(("search_experiments", {"filters": {"is_valid": False}}),), mentions=("14",),
             source="filter_test.py #11"),
    Scenario("search-by-organism", "How many experiments do we have per organism?",
             tools=(("count_experiments_by_group", {"group_by": ["organism"]}),), mentions=("yeast", "63")),
    Scenario("search-per-year", "How many experiments did we run each year?",
             tools=(("count_experiments_by_time_period", {}),), mentions=("2023", "39", "2024", "24")),
    Scenario("search-period", "List the experiments from August 2023",
             tools=(("search_experiments_in_period|search_experiments_by_date_range", {}),), mentions=("9",)),
    Scenario("search-most-recent", "What was our most recent experiment?",
             tools=(("get_most_recent_experiment", {}),), mentions=("20241028",)),
    Scenario("search-earliest", "When was the first experiment done?",
             tools=(("get_earliest_experiment", {}),), mentions=("20230405",)),
    Scenario("search-missing-tracking", "Which experiments are missing tracking files?",
             tools=(("find_experiments_with_missing_files", {}),), mentions=("32",)),
    Scenario("search-duplicates", "Are there any duplicate experiment records?",
             tools=(("find_duplicate_experiment_records", {}),)),
    Scenario("search-no-match", "Find all zebrafish experiments",
             tools=(("search_experiments", {"filters": {"organism": "zebrafish"}}),)),
]


# ---------------------------------------------------------------------------
# Insertion: validation, then insert only if the file passed
# ---------------------------------------------------------------------------

def _insert_request(name: str) -> str:
    return (
        f"Insert the experiment metadata from the CSV file located at {INSERT_FIXTURES}/{name} into the database. "
        f"Save any invalid records found during validation to {INVALID_ROWS_PATH}."
    )


INSERTION = [
    # The wording the Streamlit upload button sends (ui/app.py), minus the
    # database path: a path named in the request reaches the tool as an
    # explicit argument and would bypass the sandbox copy. The wording does
    # not say which kind of metadata the file holds, which the validation
    # agent is told to ask about when unclear.
    Scenario("insert-ui-wording",
             f"Insert the data from the CSV file located at {INSERT_FIXTURES}/valid.csv into the database. "
             f"Save any invalid records found during validation to {INVALID_ROWS_PATH}, "
             "and return any skipped/invalid rows.",
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/valid.csv"}),
                    ("insert_csv_with_report", {"csv_path": f"{INSERT_FIXTURES}/valid.csv"})),
             source="ui/app.py handle_insert_upload"),
    Scenario("insert-valid-existing-rows", _insert_request("valid.csv"),
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/valid.csv"}),
                    ("insert_csv_with_report", {"csv_path": f"{INSERT_FIXTURES}/valid.csv"})),
             source="insert_test.py insertion #2 (all rows already exist, so all are skipped)"),
    Scenario("insert-foreign-keys", _insert_request("rows_with_foreign_keys.csv"),
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/rows_with_foreign_keys.csv"}),
                    ("insert_csv_with_report", {"csv_path": f"{INSERT_FIXTURES}/rows_with_foreign_keys.csv"})),
             source="insert_test.py insertion #3"),
    Scenario("insert-blocked-mixed", _insert_request("mixed_valid_invalid.csv"),
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/mixed_valid_invalid.csv"}),),
             source="insert_test.py validation #5 (invalid rows: nothing may be inserted)"),
    Scenario("insert-blocked-missing-values", _insert_request("missing_values.csv"),
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/missing_values.csv"}),),
             source="insert_test.py validation #4"),
    Scenario("insert-blocked-bad-values", _insert_request("valid_rows_non_existing_db.csv"),
             tools=(("validate_csv", {"file_path": f"{INSERT_FIXTURES}/valid_rows_non_existing_db.csv"}),),
             source="insert_test.py insertion #1 (the file has 8 invalid rows, e.g. organism 'Drosaphila')"),
]
