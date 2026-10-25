"""Unit tests for the evaluation module: metrics, scenarios and the database sandbox.

No model is called. Invocations are built by hand in ADK's own format, the
same shape ADK records when it runs an agent.
"""

import os

import pytest
from google.adk.evaluation.eval_case import IntermediateData, Invocation, InvocationEvent, InvocationEvents
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus
from google.adk.evaluation.metric_evaluator_registry import DEFAULT_METRIC_EVALUATOR_REGISTRY
from google.genai import types

import agent.utils as utils
from agent.config import DEFAULT_DB_PATH
from agent.pydantic_models import ALLOWED_TABLES, StrictLabFilters
from evaluation import metrics, scenarios
from evaluation.runner import SUITES
from evaluation.sandbox import database_copy

pytestmark = pytest.mark.unit


# ---------- Building invocations ----------

def call(name, **args):
    return types.Part(function_call=types.FunctionCall(id=f"id-{name}", name=name, args=args))


def response(name, **result):
    return types.Part(function_response=types.FunctionResponse(id=f"id-{name}", name=name, response=result))


def recorded(*parts, answer=""):
    """An invocation as ADK records it while running the agent."""
    events = [InvocationEvent(author="agent", content=types.Content(role="model", parts=[p])) for p in parts]
    return Invocation(
        user_content=types.Content(role="user", parts=[types.Part(text="request")]),
        final_response=types.Content(role="model", parts=[types.Part(text=answer)]),
        intermediate_data=InvocationEvents(invocation_events=events),
    )


def expected(scenario):
    return scenarios.to_eval_case(scenario).conversation[0]


def evaluate(metric_class, actual, expected_invocation, threshold=1.0):
    evaluator = metric_class(EvalMetric(metric_name=metric_class.metric_name, threshold=threshold))
    return evaluator.evaluate_invocations([actual], [expected_invocation])


# ---------- routing_accuracy ----------

def test_routing_passes_when_the_transfer_matches():
    want = expected(scenarios.Scenario("x", "find yeast", route="query_agent"))
    got = recorded(call("transfer_to_agent", agent_name="query_agent"))
    assert evaluate(metrics.RoutingAccuracy, got, want).overall_score == 1.0


def test_routing_fails_on_the_wrong_specialist():
    want = expected(scenarios.Scenario("x", "delete yeast", route="delete_supervisor_agent"))
    got = recorded(call("transfer_to_agent", agent_name="query_agent"))
    result = evaluate(metrics.RoutingAccuracy, got, want)
    assert (result.overall_score, result.overall_eval_status) == (0.0, EvalStatus.FAILED)


def test_off_topic_requests_must_not_be_routed():
    want = expected(scenarios.Scenario("x", "hi", route=None))
    assert evaluate(metrics.RoutingAccuracy, recorded(answer="Hello!"), want).overall_score == 1.0
    assert evaluate(metrics.RoutingAccuracy, recorded(call("transfer_to_agent", agent_name="query_agent")), want).overall_score == 0.0


# ---------- deletion_filter_match ----------

DELETE_INVALID_MASKS = scenarios.Scenario(
    "x", "delete invalid masks", route="delete_supervisor_agent",
    table="Masks", filters={"is_valid": False}, outcome=metrics.AWAITING_APPROVAL,
)


def test_filters_are_compared_after_the_apps_own_normalisation():
    # "mask" is an alias for Masks, and "n" means the same as False.
    got = recorded(call("preview_deletion", table="mask", filters={"is_valid": "n"}))
    assert evaluate(metrics.DeletionFilterMatch, got, expected(DELETE_INVALID_MASKS)).overall_score == 1.0


def test_each_wrong_part_costs_a_third():
    got = recorded(call("preview_deletion", table="Masks", filters={"is_valid": False}, limit=10))
    assert evaluate(metrics.DeletionFilterMatch, got, expected(DELETE_INVALID_MASKS)).overall_score == pytest.approx(2 / 3)


def test_an_invented_filter_key_is_a_mismatch():
    got = recorded(call("preview_deletion", table="Masks", filters={"is_valid": False, "location": "lab1"}))
    assert evaluate(metrics.DeletionFilterMatch, got, expected(DELETE_INVALID_MASKS)).overall_score < 1.0


def test_the_filter_agent_alone_is_scored_from_its_json_answer():
    got = recorded(answer='{"db_path": null, "table": "Masks", "filters": {"is_valid": false}, "limit": null}')
    assert evaluate(metrics.DeletionFilterMatch, got, expected(DELETE_INVALID_MASKS)).overall_score == 1.0


def test_an_expected_table_of_none_accepts_any_table():
    want = expected(scenarios.Scenario("x", "delete everything", table=None, filters={}, outcome=metrics.BLOCKED))
    got = recorded(call("preview_deletion", table="Experiment", filters={}))
    assert evaluate(metrics.DeletionFilterMatch, got, want).overall_score == 1.0


def test_filter_metric_does_not_apply_to_cases_without_a_deletion():
    want = expected(scenarios.Scenario("x", "find yeast", route="query_agent"))
    assert evaluate(metrics.DeletionFilterMatch, recorded(), want).overall_eval_status == EvalStatus.NOT_EVALUATED


# ---------- deletion_outcome ----------

@pytest.mark.parametrize("parts, outcome", [
    ((call("preview_deletion"), response("preview_deletion", status="preview"), call("adk_request_confirmation")),
     metrics.AWAITING_APPROVAL),
    ((call("preview_deletion"), response("preview_deletion", status="no_matches")), metrics.NO_MATCHES),
    ((call("preview_deletion"), response("preview_deletion", status="blocked")), metrics.BLOCKED),
    ((), metrics.BLOCKED),
    ((call("execute_deletion"), response("execute_deletion", status="completed", deleted_count=3)), metrics.EXECUTED),
])
def test_outcome_is_read_from_the_recorded_tool_activity(parts, outcome):
    assert metrics.deletion_outcome(recorded(*parts)) == outcome


@pytest.mark.parametrize("scenario", scenarios.DELETION, ids=lambda s: s.id)
def test_every_deletion_scenario_encodes_the_outcome_it_declares(scenario):
    assert metrics.deletion_outcome(expected(scenario)) == scenario.outcome


def test_a_blocked_request_that_reaches_approval_fails():
    want = expected(scenarios.Scenario("x", "delete all users", table="User", filters={}, outcome=metrics.BLOCKED))
    got = recorded(call("preview_deletion"), response("preview_deletion", status="preview"), call("execute_deletion"))
    assert evaluate(metrics.DeletionOutcome, got, want).overall_score == 0.0


def test_an_executed_deletion_always_scores_zero():
    got = recorded(call("execute_deletion"), response("execute_deletion", status="completed"))
    assert evaluate(metrics.DeletionOutcome, got, expected(DELETE_INVALID_MASKS)).overall_score == 0.0


# ---------- tool_call_match ----------

INSERT_VALID = scenarios.Scenario("x", "insert", tools=(
    ("validate_csv", {"file_path": "a.csv"}), ("insert_csv_with_report", {"csv_path": "a.csv"}),
))
INSERT_REJECTED = scenarios.Scenario("x", "insert", tools=(("validate_csv", {"file_path": "a.csv"}),))


def test_expected_tools_in_order_with_extra_arguments_pass():
    got = recorded(call("validate_csv", file_path="a.csv", output_path="out.csv"), call("insert_csv_with_report", csv_path="a.csv"))
    assert evaluate(metrics.ToolCallMatch, got, expected(INSERT_VALID)).overall_score == 1.0


def test_wrong_argument_value_fails():
    got = recorded(call("validate_csv", file_path="b.csv"), call("insert_csv_with_report", csv_path="b.csv"))
    assert metrics.tool_call_mismatch(got, expected(INSERT_VALID)).startswith("missing validate_csv")


def test_inserting_after_a_rejected_validation_fails():
    got = recorded(call("validate_csv", file_path="a.csv"), call("insert_csv_with_report", csv_path="a.csv"))
    assert metrics.tool_call_mismatch(got, expected(INSERT_REJECTED)) == "unexpected write: insert_csv_with_report"


def test_either_of_two_listed_tools_is_accepted():
    want = expected(scenarios.Scenario("x", "august", tools=(("search_experiments_in_period|search_experiments_by_date_range", {}),)))
    got = recorded(call("search_experiments_by_date_range", start_date="20230801", end_date="20230831"))
    assert evaluate(metrics.ToolCallMatch, got, want).overall_score == 1.0


def test_search_filters_are_normalised_too():
    want = expected(scenarios.Scenario("x", "invalid", tools=(("search_experiments", {"filters": {"is_valid": False}}),)))
    assert evaluate(metrics.ToolCallMatch, recorded(call("search_experiments", filters={"is_valid": "N"})), want).overall_score == 1.0


# ---------- response_mentions ----------

def test_mentions_score_is_the_share_of_required_phrases_found():
    want = expected(scenarios.Scenario("x", "per year", mentions=("2023", "39", "2024", "24")))
    got = recorded(answer="In 2023 there were 39 experiments.")
    assert evaluate(metrics.ResponseMentions, got, want, threshold=0.5).overall_score == 0.5


# ---------- Scenarios ----------

def test_case_ids_are_unique_within_each_suite():
    for suite in SUITES.values():
        ids = [s.id for s in suite.scenarios]
        assert len(ids) == len(set(ids)), suite.name


DELIBERATELY_INVALID = {"delete-unknown-table", "delete-unsupported-field"}


@pytest.mark.parametrize("scenario", scenarios.DELETION + scenarios.FILTER_EXTRACTION, ids=lambda s: s.id)
def test_expected_deletions_use_real_tables_and_supported_filters(scenario):
    if scenario.id in DELIBERATELY_INVALID:
        pytest.skip("this case checks that an invalid request is blocked")
    assert scenario.table is None or scenario.table in ALLOWED_TABLES
    StrictLabFilters(**(scenario.filters or {}))


def test_insert_fixtures_exist():
    for scenario in scenarios.INSERTION:
        for _, args in scenario.tools:
            path = args.get("file_path") or args.get("csv_path")
            assert os.path.isfile(path), path


def test_custom_metrics_are_registered_with_adk():
    metrics.register_metrics()
    names = {info.metric_name for info in DEFAULT_METRIC_EVALUATOR_REGISTRY.get_registered_metrics()}
    assert {m.metric_name for m in metrics.CUSTOM_METRICS} <= names


# ---------- Sandbox ----------

def test_sandbox_points_every_tool_at_a_copy_and_restores_afterwards():
    import agent.query_agent as query_agent

    def db_default(func):
        return func.__defaults__[list(func.__code__.co_varnames).index("db_path") - func.__code__.co_argcount]

    with database_copy() as copy_path:
        assert copy_path != DEFAULT_DB_PATH and os.path.isfile(copy_path)
        assert utils.DEFAULT_DB_PATH == copy_path
        assert db_default(query_agent.search_experiments) == copy_path
        assert db_default(utils.insert_csv_with_report) == copy_path

    assert utils.DEFAULT_DB_PATH == DEFAULT_DB_PATH
    assert db_default(query_agent.search_experiments) == DEFAULT_DB_PATH
    assert db_default(utils.insert_csv_with_report) == DEFAULT_DB_PATH
