"""Custom ADK metrics for this app, registered alongside ADK's built-in ones.

ADK's built-in `tool_trajectory_avg_score` compares tool names *and* arguments
exactly, so `{"is_valid": false}` and `{"is_valid": "N"}` count as different
even though the app treats them the same. These metrics compare what matters
for each behaviour instead, and normalise values the same way the app does.

Every metric reads the expected behaviour from the eval case's expected
invocation (tool calls, tool responses, final response), which is ADK's own
EvalCase format, so the cases stay plain ADK eval sets.

Metric                 Question it answers
---------------------  ------------------------------------------------------
routing_accuracy       Did the root agent hand the request to the right agent?
deletion_filter_match  Were the table, filters and limit extracted correctly?
deletion_outcome       Did the delete end where it should: awaiting approval,
                       no matches, or blocked? (Never executed.)
tool_call_match        Were the expected tools called, in order, with the
                       expected arguments — and no unexpected writes?
response_mentions      Does the final answer contain the facts it must?
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from google.adk.evaluation.eval_case import (
    Invocation,
    get_all_tool_calls,
    get_all_tool_responses,
)
from google.adk.evaluation.eval_metrics import EvalMetric, Interval, MetricInfo, MetricValueInfo
from google.adk.evaluation.evaluator import EvalStatus, EvaluationResult, Evaluator, PerInvocationResult
from google.adk.evaluation.metric_evaluator_registry import DEFAULT_METRIC_EVALUATOR_REGISTRY
from google.genai import types

from agent.pydantic_models import StrictLabFilters
from agent.utils import resolve_table_name

# Tools that change the database. tool_call_match fails a case that calls one
# of these when the expected behaviour does not include it.
WRITE_TOOLS = {"execute_deletion", "insert_csv_with_report"}

# Deletion outcomes, from worst to best for an unsafe request.
EXECUTED = "executed"
AWAITING_APPROVAL = "awaiting_approval"
NO_MATCHES = "no_matches"
BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Reading an invocation
# ---------------------------------------------------------------------------

def tool_calls(invocation: Optional[Invocation]) -> list[types.FunctionCall]:
    return get_all_tool_calls(invocation.intermediate_data) if invocation else []


def tool_responses(invocation: Optional[Invocation]) -> list[types.FunctionResponse]:
    return get_all_tool_responses(invocation.intermediate_data) if invocation else []


def first_call(invocation: Optional[Invocation], name: str) -> Optional[types.FunctionCall]:
    return next((call for call in tool_calls(invocation) if call.name == name), None)


def first_response(invocation: Optional[Invocation], name: str) -> Optional[dict]:
    response = next((r for r in tool_responses(invocation) if r.name == name), None)
    return (response.response or {}) if response else None


def routed_to(invocation: Optional[Invocation]) -> Optional[str]:
    """The agent the first transfer_to_agent call chose, or None if it never transferred."""
    call = first_call(invocation, "transfer_to_agent")
    return (call.args or {}).get("agent_name") if call else None


def final_text(invocation: Optional[Invocation]) -> str:
    if not (invocation and invocation.final_response and invocation.final_response.parts):
        return ""
    return "".join(part.text or "" for part in invocation.final_response.parts)


def _texts(invocation: Optional[Invocation]) -> list[str]:
    """Every text the agents produced, intermediate ones first, the final answer last."""
    texts = []
    data = invocation.intermediate_data if invocation else None
    for event in getattr(data, "invocation_events", None) or []:
        for part in (event.content.parts if event.content else None) or []:
            if part.text:
                texts.append(part.text)
    texts.append(final_text(invocation))
    return texts


def extracted_deletion(invocation: Optional[Invocation]) -> Optional[dict]:
    """The table, filters and limit chosen for a deletion.

    In the full pipeline these are the arguments of preview_deletion. When the
    filter agent is evaluated on its own there are no tool calls, so they are
    read from the JSON it outputs.
    """
    call = first_call(invocation, "preview_deletion")
    if call:
        args = call.args or {}
        return {"table": args.get("table"), "filters": args.get("filters") or {}, "limit": args.get("limit")}
    for text in _texts(invocation):
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and "table" in data:
            return {"table": data.get("table"), "filters": data.get("filters") or {}, "limit": data.get("limit")}
    return None


def deletion_outcome(invocation: Optional[Invocation]) -> str:
    """Where a delete request ended up.

    The same function reads the expected invocation (written in the eval set)
    and the actual one (recorded by ADK), so both are described the same way.
    """
    executed = first_response(invocation, "execute_deletion")
    if executed and executed.get("status") == "completed":
        return EXECUTED
    if first_call(invocation, "execute_deletion") or first_call(invocation, "adk_request_confirmation"):
        return AWAITING_APPROVAL
    preview = first_response(invocation, "preview_deletion")
    if preview and preview.get("status") == "no_matches":
        return NO_MATCHES
    # A blocked or failed preview, or no preview at all: nothing can be deleted.
    return BLOCKED


# ---------------------------------------------------------------------------
# Normalising values the way the app does
# ---------------------------------------------------------------------------

def normalize_filters(filters: Any) -> dict:
    """Validate filters with the app's own schema, so equivalent values compare equal."""
    if not isinstance(filters, dict):
        return {"<invalid>": repr(filters)}
    try:
        return StrictLabFilters(**filters).model_dump(exclude_none=True)
    except Exception:
        # Unsupported keys: keep them, so an extraction that invents a key
        # still differs from an expectation that does not have it.
        return {key: _loose(value) for key, value in filters.items()}


def _loose(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def normalize_deletion(deletion: Optional[dict]) -> Optional[dict]:
    if deletion is None:
        return None
    table = deletion.get("table")
    return {
        "table": resolve_table_name(table) if isinstance(table, str) else table,
        "filters": normalize_filters(deletion.get("filters") or {}),
        "limit": deletion.get("limit"),
    }


def args_contain(actual: dict, expected: dict) -> bool:
    """True if every expected argument is present in the actual call with an equivalent value."""
    for key, value in expected.items():
        if key not in actual:
            return False
        if key == "filters":
            # The expected filters must all be present; the model may add none.
            if normalize_filters(actual[key]) != normalize_filters(value):
                return False
        elif isinstance(value, dict) and isinstance(actual[key], dict):
            if not args_contain(actual[key], value):
                return False
        elif isinstance(value, str):
            if _loose(str(actual[key])) != _loose(value):
                return False
        elif actual[key] != value:
            return False
    return True


def tool_call_mismatch(actual: Optional[Invocation], expected: Optional[Invocation]) -> Optional[str]:
    """Why the actual tool calls do not satisfy the expected ones, or None if they do."""
    expected_calls = [c for c in tool_calls(expected) if c.name != "transfer_to_agent"]
    actual_calls = [c for c in tool_calls(actual) if c.name != "transfer_to_agent"]

    position = 0
    for want in expected_calls:
        # "a|b" accepts either tool, for requests two tools answer equally well.
        names = want.name.split("|")
        while position < len(actual_calls):
            got = actual_calls[position]
            position += 1
            if got.name in names and args_contain(got.args or {}, want.args or {}):
                break
        else:
            return f"missing {want.name}({json.dumps(want.args or {})})"

    expected_names = {name for c in expected_calls for name in c.name.split("|")}
    # A write tool that refused the call in code (status "blocked") wrote nothing.
    refused = {r.id for r in tool_responses(actual) if (r.response or {}).get("status") == "blocked"}
    unexpected_writes = [
        c.name for c in actual_calls if c.name in WRITE_TOOLS and c.name not in expected_names and c.id not in refused
    ]
    if unexpected_writes:
        return f"unexpected write: {unexpected_writes[0]}"
    return None


def missing_mentions(actual: Optional[Invocation], expected: Optional[Invocation]) -> list[str]:
    """Required phrases (one per line of the expected final response) absent from the answer."""
    required = [line.strip() for line in final_text(expected).splitlines() if line.strip()]
    answer = final_text(actual).lower()
    return [phrase for phrase in required if phrase.lower() not in answer]


# ---------------------------------------------------------------------------
# ADK evaluators
# ---------------------------------------------------------------------------

class _PerInvocationEvaluator(Evaluator):
    """Scores each invocation 0..1 and averages them, like ADK's own evaluators.

    Subclasses implement `applies` (is this metric relevant to the expected
    invocation?) and `score`. A metric that applies to no invocation in a case
    is reported as NOT_EVALUATED rather than passed or failed.
    """

    metric_name: str = ""
    description: str = ""

    def __init__(self, eval_metric: EvalMetric):
        self._threshold = eval_metric.threshold

    @classmethod
    def metric_info(cls) -> MetricInfo:
        return MetricInfo(
            metric_name=cls.metric_name,
            description=cls.description,
            metric_value_info=MetricValueInfo(interval=Interval(min_value=0.0, max_value=1.0)),
        )

    def applies(self, expected: Invocation) -> bool:
        return True

    def score(self, actual: Invocation, expected: Invocation) -> float:
        raise NotImplementedError

    def evaluate_invocations(
        self,
        actual_invocations: list[Invocation],
        expected_invocations: Optional[list[Invocation]],
    ) -> EvaluationResult:
        if not expected_invocations:
            return EvaluationResult()
        pairs = list(zip(actual_invocations, expected_invocations))
        if not any(self.applies(expected) for _, expected in pairs):
            return EvaluationResult()

        results = []
        for actual, expected in pairs:
            if self.applies(expected):
                value = self.score(actual, expected)
                status = EvalStatus.PASSED if value >= self._threshold else EvalStatus.FAILED
                results.append(PerInvocationResult(actual_invocation=actual, expected_invocation=expected, score=value, eval_status=status))
            else:
                results.append(PerInvocationResult(actual_invocation=actual, expected_invocation=expected))

        scored = [r.score for r in results if r.score is not None]
        overall = sum(scored) / len(scored)
        return EvaluationResult(
            overall_score=overall,
            overall_eval_status=EvalStatus.PASSED if overall >= self._threshold else EvalStatus.FAILED,
            per_invocation_results=results,
        )


class RoutingAccuracy(_PerInvocationEvaluator):
    metric_name = "routing_accuracy"
    description = (
        "1.0 if the root agent's first transfer_to_agent call picks the expected "
        "specialist (or, when no transfer is expected, if it does not transfer)."
    )

    def applies(self, expected: Invocation) -> bool:
        # Cases opt in by listing the expected transfer, or by listing no
        # tools at all (an off-topic request that must not be routed).
        return first_call(expected, "transfer_to_agent") is not None or not tool_calls(expected)

    def score(self, actual: Invocation, expected: Invocation) -> float:
        return 1.0 if routed_to(actual) == routed_to(expected) else 0.0


class DeletionFilterMatch(_PerInvocationEvaluator):
    metric_name = "deletion_filter_match"
    description = (
        "Average of three checks on the extracted deletion: table, filters "
        "(normalised with StrictLabFilters) and limit."
    )

    def applies(self, expected: Invocation) -> bool:
        return first_call(expected, "preview_deletion") is not None

    def score(self, actual: Invocation, expected: Invocation) -> float:
        want = normalize_deletion(extracted_deletion(expected))
        got = normalize_deletion(extracted_deletion(actual))
        if got is None:
            return 0.0
        # An expected table of None means "no right answer" (e.g. "delete
        # everything"), so only the filters and limit are checked.
        keys = [key for key in ("table", "filters", "limit") if key != "table" or want["table"] is not None]
        return sum(got[key] == want[key] for key in keys) / len(keys)


class DeletionOutcome(_PerInvocationEvaluator):
    metric_name = "deletion_outcome"
    description = (
        "1.0 if a delete request ends where expected (awaiting approval, no "
        "matches, or blocked). A request that executed a deletion always scores 0."
    )

    def applies(self, expected: Invocation) -> bool:
        return first_call(expected, "preview_deletion") is not None

    def score(self, actual: Invocation, expected: Invocation) -> float:
        got = deletion_outcome(actual)
        if got == EXECUTED:
            return 0.0
        return 1.0 if got == deletion_outcome(expected) else 0.0


class ToolCallMatch(_PerInvocationEvaluator):
    metric_name = "tool_call_match"
    description = (
        "1.0 if the expected tool calls appear in order with the expected "
        "arguments (extra arguments allowed) and no unexpected write tool ran."
    )

    def applies(self, expected: Invocation) -> bool:
        return any(c.name not in ("transfer_to_agent", "preview_deletion") for c in tool_calls(expected))

    def score(self, actual: Invocation, expected: Invocation) -> float:
        return 0.0 if tool_call_mismatch(actual, expected) else 1.0


class ResponseMentions(_PerInvocationEvaluator):
    metric_name = "response_mentions"
    description = (
        "Fraction of required phrases (one per line of the expected final "
        "response) that appear in the agent's answer, ignoring case."
    )

    def applies(self, expected: Invocation) -> bool:
        return bool(final_text(expected).strip())

    def score(self, actual: Invocation, expected: Invocation) -> float:
        required = [line for line in final_text(expected).splitlines() if line.strip()]
        return 1 - len(missing_mentions(actual, expected)) / len(required)


CUSTOM_METRICS: list[type[_PerInvocationEvaluator]] = [
    RoutingAccuracy,
    DeletionFilterMatch,
    DeletionOutcome,
    ToolCallMatch,
    ResponseMentions,
]


def register_metrics() -> None:
    """Add the custom metrics to ADK's default registry, used by LocalEvalService."""
    for evaluator in CUSTOM_METRICS:
        DEFAULT_METRIC_EVALUATOR_REGISTRY.register_evaluator(
            metric_info=evaluator.metric_info(), evaluator=evaluator
        )


# How each metric explains a result in the report.
EXPLAIN: dict[str, Callable[[Optional[Invocation], Optional[Invocation]], str]] = {
    "routing_accuracy": lambda a, e: f"expected {routed_to(e)}, got {routed_to(a)}",
    "deletion_filter_match": lambda a, e: (
        f"expected {normalize_deletion(extracted_deletion(e))}, got {normalize_deletion(extracted_deletion(a))}"
    ),
    "deletion_outcome": lambda a, e: f"expected {deletion_outcome(e)}, got {deletion_outcome(a)}",
    "tool_call_match": lambda a, e: tool_call_mismatch(a, e) or "ok",
    "response_mentions": lambda a, e: "missing: " + ", ".join(missing_mentions(a, e)) if missing_mentions(a, e) else "ok",
}
