"""Unit tests for deletion preview, execution, and state cleanup."""

import inspect
from types import SimpleNamespace

import pytest

import agent.utils as utils
from agent.config import DEFAULT_DB_PATH

pytestmark = pytest.mark.unit


# ---------- resolve_table_name ----------

@pytest.mark.parametrize("raw, expected", [
    ("track", "TrackingFiles"),
    ("Tracking files", "TrackingFiles"),
    ("raw files", "RawFiles"),
    ("Masks", "Masks"),
    ("Spaceships", "Spaceships"),
])
def test_resolve_table_name(raw, expected):
    assert utils.resolve_table_name(raw) == expected


@pytest.mark.xfail(strict=True, reason="Known bug: aliases match only the singular word, so 'masks' is not resolved")
@pytest.mark.parametrize("raw, expected", [("masks", "Masks"), ("experiments", "Experiment")])
def test_plural_table_names_are_resolved(raw, expected):
    assert utils.resolve_table_name(raw) == expected


# ---------- validate_filters ----------

def test_validate_filters_normalizes_valid_filters():
    assert utils.validate_filters({"organism": "yeast", "is_valid": False}) == (
        {"organism": "yeast", "is_valid": "N"},
        None,
    )


def test_validate_filters_accepts_no_filters():
    assert utils.validate_filters(None) == ({}, None)


def test_validate_filters_reports_unknown_keys():
    clean, error = utils.validate_filters({"colour": "blue"})
    assert clean == {}
    assert error.startswith("Invalid filter fields")


# ---------- _sanitize_limit ----------

@pytest.mark.parametrize("text", [
    "delete 5 records",
    "remove the first 3 rows",
    "show the top 10 entries",
    "limited to 20 items",
    "delete 2 files",
])
def test_limit_is_kept_when_the_user_asked_for_a_count(make_tool_context, text):
    assert utils._sanitize_limit(make_tool_context(text), 5) == 5


@pytest.mark.parametrize("text", [
    "delete all invalid tracking files",
    "remove every record from 2023",
    "delete experiments from August 3rd",
])
def test_invented_limit_is_dropped(make_tool_context, text):
    assert utils._sanitize_limit(make_tool_context(text), 10) is None


def test_no_limit_stays_none(make_tool_context):
    assert utils._sanitize_limit(make_tool_context("delete 5 records"), None) is None


def test_limit_is_dropped_when_the_user_text_cannot_be_read():
    assert utils._sanitize_limit(SimpleNamespace(state={}), 10) is None


@pytest.mark.xfail(strict=True, reason="Known weakness: the regex reads '3 files' as an explicit count")
def test_count_inside_a_description_is_not_treated_as_a_limit(make_tool_context):
    ctx = make_tool_context("delete all records for the 3 files uploaded yesterday")
    assert utils._sanitize_limit(ctx, 10) is None


# ---------- preview_deletion: blocked before touching the database ----------

def test_empty_filters_are_blocked(make_tool_context, fake_delete):
    result = utils.preview_deletion(make_tool_context(), table="TrackingFiles", filters={})
    assert result["status"] == "blocked"
    assert fake_delete.calls == []


def test_missing_table_is_blocked(make_tool_context, fake_delete):
    result = utils.preview_deletion(make_tool_context(), table="", filters={"organism": "yeast"})
    assert result["status"] == "blocked"
    assert fake_delete.calls == []


def test_unknown_table_is_blocked(make_tool_context, fake_delete):
    result = utils.preview_deletion(make_tool_context(), table="Spaceships", filters={"organism": "yeast"})
    assert result["status"] == "blocked"
    assert fake_delete.calls == []


def test_unknown_filter_key_is_blocked(make_tool_context, fake_delete):
    result = utils.preview_deletion(make_tool_context(), table="Masks", filters={"colour": "blue"})
    assert result["status"] == "blocked"
    assert fake_delete.calls == []


# ---------- preview_deletion: dry run and snapshot ----------

def test_preview_runs_a_dry_run_and_saves_the_snapshot(make_tool_context, fake_delete):
    ctx = make_tool_context()
    result = utils.preview_deletion(ctx, table="track", filters={"is_valid": False})

    assert result["status"] == "preview"
    assert result["preview_count"] == 3
    assert fake_delete.calls == [
        {"db_path": DEFAULT_DB_PATH, "table": "TrackingFiles", "filters": {"is_valid": "N"}, "limit": None, "dry_run": True}
    ]
    assert ctx.state["pending_deletion"] == {
        "db_path": DEFAULT_DB_PATH,
        "table": "TrackingFiles",
        "filters": {"is_valid": "N"},
        "limit": None,
        "preview_count": 3,
        "preview_path": "/tmp/preview.csv",
    }


def test_preview_uses_the_database_the_user_named(make_tool_context, fake_delete):
    utils.preview_deletion(make_tool_context(), table="Masks", filters={"organism": "yeast"}, db_path="/data/lab.db")
    assert fake_delete.calls[0]["db_path"] == "/data/lab.db"


def test_preview_drops_an_invented_limit_before_the_dry_run(make_tool_context, fake_delete):
    ctx = make_tool_context("delete all invalid tracking files")
    utils.preview_deletion(ctx, table="TrackingFiles", filters={"is_valid": "N"}, limit=10)
    assert fake_delete.calls[0]["limit"] is None
    assert ctx.state["pending_deletion"]["limit"] is None


def test_no_matches_clears_any_old_snapshot(make_tool_context, fake_delete):
    fake_delete.preview_count = 0
    ctx = make_tool_context(state={"pending_deletion": {"table": "Masks"}})
    result = utils.preview_deletion(ctx, table="Masks", filters={"organism": "yeast"})
    assert result["status"] == "no_matches"
    assert ctx.state["pending_deletion"] is None


def test_preview_failure_clears_the_snapshot(make_tool_context, fake_delete):
    fake_delete.error = RuntimeError("database locked")
    ctx = make_tool_context(state={"pending_deletion": {"table": "Masks"}})
    result = utils.preview_deletion(ctx, table="Masks", filters={"organism": "yeast"})
    assert result["status"] == "error"
    assert ctx.state["pending_deletion"] is None


# ---------- execute_deletion ----------

SNAPSHOT = {"db_path": "lab.db", "table": "Masks", "filters": {"organism": "yeast"}, "limit": None, "preview_count": 3}


def test_execute_takes_no_arguments_so_the_model_cannot_pass_new_filters():
    assert list(inspect.signature(utils.execute_deletion).parameters) == ["tool_context"]


def test_execute_without_a_snapshot_returns_an_error(make_tool_context, fake_delete):
    result = utils.execute_deletion(make_tool_context(confirmed=True))
    assert result["status"] == "error"
    assert fake_delete.calls == []


def test_execute_without_confirmation_deletes_nothing(make_tool_context, fake_delete):
    ctx = make_tool_context(state={"pending_deletion": SNAPSHOT})
    result = utils.execute_deletion(ctx)
    assert result["status"] == "error"
    assert fake_delete.calls == []
    assert ctx.state["pending_deletion"] is None


def test_denial_deletes_nothing_and_clears_the_snapshot(make_tool_context, fake_delete):
    ctx = make_tool_context(confirmed=False, state={"pending_deletion": SNAPSHOT})
    result = utils.execute_deletion(ctx)
    assert result["status"] == "cancelled"
    assert fake_delete.calls == []
    assert ctx.state["pending_deletion"] is None


def test_approval_deletes_exactly_what_was_previewed(make_tool_context, fake_delete):
    ctx = make_tool_context(confirmed=True, state={"pending_deletion": SNAPSHOT})
    result = utils.execute_deletion(ctx)
    assert result["status"] == "completed"
    assert result["deleted_count"] == 3
    assert fake_delete.calls == [
        {"db_path": "lab.db", "table": "Masks", "filters": {"organism": "yeast"}, "limit": None, "dry_run": False}
    ]
    assert ctx.state["pending_deletion"] is None


def test_failed_deletion_still_clears_the_snapshot(make_tool_context, fake_delete):
    fake_delete.error = RuntimeError("database locked")
    ctx = make_tool_context(confirmed=True, state={"pending_deletion": SNAPSHOT})
    result = utils.execute_deletion(ctx)
    assert result["status"] == "error"
    assert ctx.state["pending_deletion"] is None


def test_unexpected_database_result_is_reported_as_an_error(make_tool_context, fake_delete):
    fake_delete.execute_result = ["not", "a", "dict"]
    ctx = make_tool_context(confirmed=True, state={"pending_deletion": SNAPSHOT})
    assert utils.execute_deletion(ctx)["status"] == "error"
