"""Agent evaluations for root routing decisions."""

import pytest

pytestmark = pytest.mark.agent_eval


def test_root_agent_routes_requests_to_the_right_specialist(suite_results):
    runs, summary, _ = suite_results("routing")
    assert summary["routing_accuracy"]["pass_rate"] >= 0.9, [r.case_id for r in runs if r.metrics["routing_accuracy"].passed is False]
