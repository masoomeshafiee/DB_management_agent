"""Agent evaluations for the query agent's tool choice and answers."""

import pytest

pytestmark = pytest.mark.agent_eval


def test_query_agent_picks_the_right_tool(suite_results):
    runs, summary, _ = suite_results("search")
    assert summary["tool_call_match"]["pass_rate"] >= 0.8, [
        r.case_id for r in runs if r.metrics["tool_call_match"].passed is False
    ]


def test_answers_report_the_facts_the_tools_returned(suite_results):
    runs, summary, _ = suite_results("search")
    assert summary["response_mentions"]["mean_score"] >= 0.8, [
        r.case_id for r in runs if r.metrics["response_mentions"].passed is False
    ]
