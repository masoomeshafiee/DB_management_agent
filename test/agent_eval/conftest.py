"""Agent evaluations as pytest tests: each suite must reach a minimum score.

These call Gemini, so they only run when asked for:

    RUN_AGENT_EVAL=1 pytest test/agent_eval -v

For the full report (every case, every failure) use `python -m evaluation`.
"""

import asyncio
import os

import pytest

from evaluation.report import metric_summary, safety_summary
from evaluation.runner import SUITES, run_suite


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_AGENT_EVAL") == "1" and os.getenv("GOOGLE_API_KEY"):
        return
    skip = pytest.mark.skip(reason="agent evals call Gemini; set RUN_AGENT_EVAL=1 (and GOOGLE_API_KEY) to run them")
    for item in items:
        if "agent_eval" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def suite_results():
    """Run each suite at most once per test session, however many tests read it."""
    cache = {}

    def get(name):
        if name not in cache:
            runs = asyncio.run(run_suite(SUITES[name]))
            cache[name] = (runs, metric_summary(runs), safety_summary(runs))
        return cache[name]

    return get
