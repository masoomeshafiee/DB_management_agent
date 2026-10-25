"""Agent evaluations for the insert pipeline: validate first, insert only valid files."""

import pytest

pytestmark = pytest.mark.agent_eval


def test_a_rejected_file_is_never_inserted(suite_results):
    runs, _, _ = suite_results("insertion")
    unexpected_inserts = [
        r.case_id for r in runs
        if r.metrics.get("tool_call_match") and r.metrics["tool_call_match"].explanation.startswith("unexpected write")
    ]
    assert unexpected_inserts == []


def test_files_are_validated_then_inserted(suite_results):
    runs, summary, _ = suite_results("insertion")
    assert summary["tool_call_match"]["pass_rate"] >= 0.8, [
        r.case_id for r in runs if r.metrics["tool_call_match"].passed is False
    ]
