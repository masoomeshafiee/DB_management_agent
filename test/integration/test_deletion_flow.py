"""Integration tests for deletion preview and confirmation against a real SQLite copy.

The LLM is not involved: these call the deletion tools directly with a fake
ToolContext, but the database layer (lab_data_manager) and SQLite are real.
That catches the kind of bug a mocked database hides, such as filters that
validate fine but never match the values the database actually stores.
"""

import os
from types import SimpleNamespace

import pytest

import agent.utils as utils
from agent.pydantic_models import ALLOWED_TABLES
from .db_helpers import count_rows

pytestmark = pytest.mark.integration

INVALID_RAW_FILES_SQL = """
    SELECT COUNT(*) FROM RawFiles r
    JOIN Experiment e ON r.experiment_id = e.id
    WHERE e.is_valid = 'N'
"""


def raw_files(db_path):
    return count_rows(db_path, "SELECT COUNT(*) FROM RawFiles")


def test_preview_finds_rows_without_deleting_them(lab_db, make_tool_context):
    before = raw_files(lab_db)

    result = utils.preview_deletion(make_tool_context(), table="RawFiles", filters={"is_valid": False}, db_path=lab_db)

    assert result["status"] == "preview"
    assert result["preview_count"] > 0
    assert os.path.exists(result["preview_path"])
    assert raw_files(lab_db) == before


def test_is_valid_false_matches_the_rows_stored_as_n(lab_db, make_tool_context):
    result = utils.preview_deletion(
        make_tool_context(), table="RawFiles", filters={"is_valid": False}, db_path=lab_db
    )
    assert result["preview_count"] == count_rows(lab_db, INVALID_RAW_FILES_SQL)


def test_approved_deletion_removes_exactly_the_previewed_rows(lab_db, make_tool_context):
    before = raw_files(lab_db)
    ctx = make_tool_context()
    preview = utils.preview_deletion(ctx, table="RawFiles", filters={"is_valid": False}, db_path=lab_db)

    ctx.tool_confirmation = SimpleNamespace(confirmed=True)
    result = utils.execute_deletion(ctx)

    assert result["status"] == "completed"
    assert result["deleted_count"] == preview["preview_count"]
    assert raw_files(lab_db) == before - preview["preview_count"]
    again = utils.preview_deletion(make_tool_context(), table="RawFiles", filters={"is_valid": False}, db_path=lab_db)
    assert again["status"] == "no_matches"


def test_denied_deletion_changes_nothing(lab_db, make_tool_context):
    before = raw_files(lab_db)
    ctx = make_tool_context()
    utils.preview_deletion(ctx, table="RawFiles", filters={"is_valid": False}, db_path=lab_db)

    ctx.tool_confirmation = SimpleNamespace(confirmed=False)
    result = utils.execute_deletion(ctx)

    assert result["status"] == "cancelled"
    assert raw_files(lab_db) == before


def test_explicit_limit_caps_the_deletion(lab_db, make_tool_context):
    before = raw_files(lab_db)
    ctx = make_tool_context("delete 2 records of invalid raw files")
    preview = utils.preview_deletion(ctx, table="RawFiles", filters={"is_valid": False}, db_path=lab_db, limit=2)

    ctx.tool_confirmation = SimpleNamespace(confirmed=True)
    utils.execute_deletion(ctx)

    assert preview["preview_count"] == 2
    assert raw_files(lab_db) == before - 2


@pytest.mark.parametrize("table", [
    pytest.param(
        name,
        marks=pytest.mark.xfail(strict=True, reason="Known bug: the real table is AnalysisResultExperiments"),
    ) if name == "AnalysisResultExperiment" else name
    for name in sorted(ALLOWED_TABLES)
])
def test_every_allowed_table_exists_in_the_database(lab_db, table):
    assert count_rows(lab_db, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)) == 1
