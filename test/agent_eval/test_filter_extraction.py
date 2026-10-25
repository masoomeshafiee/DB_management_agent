"""Agent evaluations for structured deletion-filter extraction."""

import pytest

pytestmark = pytest.mark.agent_eval


def test_filter_agent_extracts_table_filters_and_limit(suite_results):
    runs, summary, _ = suite_results("filter_extraction")
    assert summary["deletion_filter_match"]["mean_score"] >= 0.85, [
        r.case_id for r in runs if r.metrics["deletion_filter_match"].passed is False
    ]
