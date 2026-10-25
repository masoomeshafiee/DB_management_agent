"""Unit tests for agent tools, schemas, and workflow wiring.

These lock in the configuration the safety design depends on, so a refactor
cannot silently remove a confirmation gate or reorder a pipeline.
"""

import pytest

from agent.delete_agent import delete_agent
from agent.delete_supervisor_agent import delete_supervisor_agent
from agent.filter_agent import filter_infer_agent
from agent.insert_supervisor_agent import insert_supervisor_agent
from agent.pydantic_models import DeletionSchema
from agent.query_agent import query_agent
from agent.root_agent import root_agent

pytestmark = pytest.mark.unit


def tool_names(agent):
    return [getattr(tool, "name", getattr(tool, "__name__", None)) for tool in agent.tools]


def tool_named(agent, name):
    return next(tool for tool in agent.tools if getattr(tool, "name", None) == name)


def test_execute_deletion_requires_human_confirmation():
    assert tool_named(delete_agent, "execute_deletion")._require_confirmation is True


def test_preview_deletion_runs_without_confirmation():
    assert tool_named(delete_agent, "preview_deletion")._require_confirmation is False


def test_delete_pipeline_extracts_filters_before_deleting():
    assert [a.name for a in delete_supervisor_agent.sub_agents] == ["filter_infer_agent", "delete_agent"]


def test_insert_pipeline_validates_before_inserting():
    assert [a.name for a in insert_supervisor_agent.sub_agents] == ["data_validation_agent", "insert_agent"]


def test_filter_agent_hands_structured_filters_to_the_delete_agent():
    assert filter_infer_agent.output_schema is DeletionSchema
    assert filter_infer_agent.output_key == "filters"
    assert "{filters}" in delete_agent.instruction


def test_query_agent_has_no_tool_that_can_delete():
    assert not any("delet" in name for name in tool_names(query_agent))


def test_query_agent_cannot_keep_follow_up_messages_away_from_the_router():
    assert query_agent.disallow_transfer_to_parent is True


def test_root_agent_routes_to_the_three_specialists():
    assert {a.name for a in root_agent.sub_agents} == {
        "query_agent",
        "insert_supervisor_agent",
        "delete_supervisor_agent",
    }
