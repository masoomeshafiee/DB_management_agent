"""Run evaluation suites with ADK's LocalEvalService and collect the results.

Each suite pairs a list of scenarios with the agent under test and the metrics
that judge it. Cases run one at a time with a pause between them, and a case
that hits the Gemini rate limit (429) is retried after the quota window, so
the eval works on the free tier.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable, Optional

from google.adk.agents import Agent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.evaluation.base_eval_service import (
    EvaluateConfig,
    EvaluateRequest,
    InferenceConfig,
    InferenceRequest,
    InferenceResult,
    InferenceStatus,
)
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.in_memory_eval_sets_manager import InMemoryEvalSetsManager
from google.adk.evaluation.local_eval_service import LocalEvalService
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.root_agent import root_agent

from . import scenarios
from .metrics import EXPLAIN, deletion_outcome, extracted_deletion, final_text, register_metrics, routed_to, tool_calls
from .sandbox import database_copy
from observability.token_usage import empty_usage, usage_from_events

# Where ADK's eval service stores a case's session when the case has no
# session_input (ours don't): needed to read the session's events back.
EVAL_SESSION_APP_NAME = "EvaluationGenerator"
EVAL_USER_ID = "test_user_id"

APP_NAME = "db_management_agent_eval"
RATE_LIMIT_WAIT_SECONDS = 65
MAX_RATE_LIMIT_RETRIES = 3
WORK_DIR = os.path.join(os.path.dirname(__file__), ".work")


# ---------------------------------------------------------------------------
# Agents under test
# ---------------------------------------------------------------------------

class _RoutingStub(BaseAgent):
    """Stands in for a specialist so the routing suite stops at the transfer."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(role="model", parts=[types.Part(text=f"[{self.name} would handle this]")]),
        )


def routing_agent() -> BaseAgent:
    """The real root agent (same model and prompt) with its specialists replaced by stubs.

    Routing depends only on the root prompt and the specialists' names and
    descriptions, so this measures it with one model call per case instead
    of running the whole pipeline.
    """
    return Agent(
        name=root_agent.name,
        model=root_agent.model,
        description=root_agent.description,
        instruction=root_agent.instruction,
        sub_agents=[_RoutingStub(name=a.name, description=a.description) for a in root_agent.sub_agents],
    )


def sub_agent(name: str) -> Callable[[], BaseAgent]:
    return lambda: root_agent.find_agent(name)


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------

@dataclass
class Suite:
    name: str
    description: str
    scenarios: list
    build_agent: Callable[[], BaseAgent]
    # metric name -> threshold a single case must reach to pass
    metrics: dict[str, float]
    include_route: bool = True

    def eval_set(self):
        return scenarios.to_eval_set(self.name, self.description, self.scenarios, self.include_route)


SUITES: dict[str, Suite] = {
    suite.name: suite
    for suite in [
        Suite("routing", "Root agent picks the right specialist (specialists stubbed).",
              scenarios.ROUTING, routing_agent, {"routing_accuracy": 1.0}),
        Suite("filter_extraction", "Filter agent alone: table, filters and limit from plain English.",
              scenarios.FILTER_EXTRACTION, sub_agent("filter_infer_agent"), {"deletion_filter_match": 1.0},
              include_route=False),
        Suite("deletion", "Full delete pipeline from the root agent, on a database copy. Never approved.",
              scenarios.DELETION, lambda: root_agent,
              {"routing_accuracy": 1.0, "deletion_filter_match": 1.0, "deletion_outcome": 1.0}),
        Suite("search", "Query agent alone: right tool, right arguments, right facts in the answer.",
              scenarios.SEARCH, sub_agent("query_agent"), {"tool_call_match": 1.0, "response_mentions": 1.0},
              include_route=False),
        Suite("insertion", "Insert pipeline alone: validate first, insert only if the file passed.",
              scenarios.INSERTION, sub_agent("insert_supervisor_agent"), {"tool_call_match": 1.0},
              include_route=False),
    ]
}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class MetricOutcome:
    score: Optional[float]
    passed: Optional[bool]          # None when the metric did not apply to the case
    explanation: str = ""


@dataclass
class CaseRun:
    suite: str
    case_id: str
    run: int
    request: str
    source: str
    error: Optional[str] = None
    metrics: dict[str, MetricOutcome] = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    seconds: float = 0.0
    usage: dict = field(default_factory=empty_usage)


def _observed(invocation) -> dict:
    """What the agent actually did, in a form a person can read in the report."""
    return {
        "routed_to": routed_to(invocation),
        "tools": [c.name for c in tool_calls(invocation)],
        "deletion": extracted_deletion(invocation),
        "deletion_outcome": deletion_outcome(invocation),
        "answer": final_text(invocation)[:500],
    }


def _is_rate_limit(message: Optional[str]) -> bool:
    return bool(message) and ("429" in message or "RESOURCE_EXHAUSTED" in message)


async def _infer_case(service: LocalEvalService, eval_set_id: str, case_id: str, log) -> InferenceResult:
    request = InferenceRequest(
        app_name=APP_NAME,
        eval_set_id=eval_set_id,
        eval_case_ids=[case_id],
        inference_config=InferenceConfig(parallelism=1),
    )
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        result = None
        async with contextlib.aclosing(service.perform_inference(inference_request=request)) as results:
            async for result in results:
                pass
        if result.status != InferenceStatus.FAILURE or not _is_rate_limit(result.error_message):
            return result
        if attempt < MAX_RATE_LIMIT_RETRIES:
            log(f"    rate limited, waiting {RATE_LIMIT_WAIT_SECONDS}s (retry {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})")
            await asyncio.sleep(RATE_LIMIT_WAIT_SECONDS)
    return result


async def run_suite(
    suite: Suite,
    runs: int = 1,
    pause: float = 4.0,
    case_ids: Optional[list[str]] = None,
    log: Callable[[str], None] = print,
) -> list[CaseRun]:
    """Run every case of a suite `runs` times and score it. Requires GOOGLE_API_KEY."""
    register_metrics()
    eval_set = suite.eval_set()
    by_id = {s.id: s for s in suite.scenarios}
    cases = [c for c in eval_set.eval_cases if not case_ids or c.eval_id in case_ids]

    manager = InMemoryEvalSetsManager()
    manager.create_eval_set(app_name=APP_NAME, eval_set_id=eval_set.eval_set_id)
    for case in cases:
        manager.add_eval_case(app_name=APP_NAME, eval_set_id=eval_set.eval_set_id, eval_case=case)
    # Our own session store, so each case's events (and their token usage) can be read back.
    sessions = InMemorySessionService()
    service = LocalEvalService(root_agent=suite.build_agent(), eval_sets_manager=manager, session_service=sessions)

    os.makedirs(WORK_DIR, exist_ok=True)
    runs_by_key: dict[tuple[str, int], CaseRun] = {}
    inferences: list[tuple[CaseRun, InferenceResult]] = []

    # lab_data_manager prints debug output; keep it out of the progress log.
    with open(os.path.join(WORK_DIR, "tool_output.log"), "a") as tool_output, database_copy():
        for run in range(1, runs + 1):
            for case in cases:
                scenario = by_id[case.eval_id]
                case_run = CaseRun(suite.name, case.eval_id, run, scenario.request, scenario.source)
                log(f"  [{suite.name}] {case.eval_id} (run {run}/{runs})")
                started = time.monotonic()
                with contextlib.redirect_stdout(tool_output):
                    result = await _infer_case(service, eval_set.eval_set_id, case.eval_id, log)
                case_run.seconds = round(time.monotonic() - started, 1)
                session = await sessions.get_session(
                    app_name=EVAL_SESSION_APP_NAME, user_id=EVAL_USER_ID, session_id=result.session_id
                )
                if session:
                    case_run.usage = usage_from_events(session.events)
                if result.status == InferenceStatus.SUCCESS and len(result.inferences or []) == len(case.conversation):
                    inferences.append((case_run, result))
                    case_run.observed = _observed(result.inferences[0])
                elif result.status == InferenceStatus.SUCCESS:
                    # ADK can only score a run with one turn per expected turn.
                    case_run.error = f"expected {len(case.conversation)} turn(s), got {len(result.inferences or [])}"
                    log(f"    error: {case_run.error}")
                else:
                    case_run.error = result.error_message or "inference failed"
                    log(f"    error: {case_run.error[:200]}")
                runs_by_key[(case.eval_id, run)] = case_run
                await asyncio.sleep(pause)

    if inferences:
        await _score(service, suite, inferences)
    return list(runs_by_key.values())


async def _score(service: LocalEvalService, suite: Suite, inferences: list[tuple[CaseRun, InferenceResult]]) -> None:
    """Evaluate every successful inference with the suite's metrics (no model calls)."""
    metrics = [EvalMetric(metric_name=name, threshold=threshold) for name, threshold in suite.metrics.items()]
    by_session = {result.session_id: case_run for case_run, result in inferences}
    request = EvaluateRequest(
        inference_results=[result for _, result in inferences],
        evaluate_config=EvaluateConfig(eval_metrics=metrics),
    )
    async with contextlib.aclosing(service.evaluate(evaluate_request=request)) as results:
        async for case_result in results:
            case_run = by_session[case_result.session_id]
            per_invocation = case_result.eval_metric_result_per_invocation[0]
            actual, expected = per_invocation.actual_invocation, per_invocation.expected_invocation
            for metric_result in case_result.overall_eval_metric_results:
                name = metric_result.metric_name
                if metric_result.score is None:
                    case_run.metrics[name] = MetricOutcome(score=None, passed=None)
                    continue
                passed = metric_result.score >= suite.metrics[name]
                case_run.metrics[name] = MetricOutcome(
                    score=round(metric_result.score, 3),
                    passed=passed,
                    explanation="" if passed else EXPLAIN[name](actual, expected),
                )


async def run_suites(names: list[str], **kwargs) -> dict[str, list[CaseRun]]:
    return {name: await run_suite(SUITES[name], **kwargs) for name in names}
