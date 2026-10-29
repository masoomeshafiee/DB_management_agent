"""Integration tests for CSV insertion against a real SQLite copy."""

import pytest

import agent.utils as utils
from .db_helpers import INSERTION_FIXTURES, table_counts

pytestmark = pytest.mark.integration


@pytest.fixture
def first_rows_csv(tmp_path):
    """The header plus five rows of valid.csv, all of which already exist in the sample database."""
    lines = (INSERTION_FIXTURES / "valid.csv").read_text().splitlines(keepends=True)
    path = tmp_path / "first_rows.csv"
    path.write_text("".join(lines[:6]))
    return str(path)


def test_rows_that_already_exist_are_skipped_not_duplicated(lab_db, make_tool_context, first_rows_csv):
    before = table_counts(lab_db)
    ctx = make_tool_context()
    utils._record_validation(ctx, first_rows_csv, [])

    result = utils.insert_csv_with_report(ctx, csv_path=first_rows_csv, db_path=lab_db)

    assert result["status"] == "completed"
    assert (result["inserted_count"], result["skipped_count"]) == (0, 5)
    assert len(ctx.state["last_insert_result"]["skipped_rows"]) == 5
    assert table_counts(lab_db) == before


def test_a_failed_insert_leaves_the_database_unchanged(lab_db, make_tool_context):
    """mixed_valid_invalid.csv makes lab_data_manager raise partway through.

    The wrapper reports an error, and because the package only commits at the
    end, none of the rows processed before the failure are kept.
    """
    before = table_counts(lab_db)
    csv_path = str(INSERTION_FIXTURES / "mixed_valid_invalid.csv")
    ctx = make_tool_context()
    # Marked as passed so the insert itself runs and fails inside the package.
    utils._record_validation(ctx, csv_path, [])

    result = utils.insert_csv_with_report(ctx, csv_path=csv_path, db_path=lab_db)

    assert result["status"] == "error"
    assert table_counts(lab_db) == before


def test_an_unvalidated_file_is_blocked_and_the_database_is_unchanged(lab_db, make_tool_context):
    before = table_counts(lab_db)
    result = utils.insert_csv_with_report(
        make_tool_context(), csv_path=str(INSERTION_FIXTURES / "mixed_valid_invalid.csv"), db_path=lab_db
    )
    assert result["status"] == "blocked"
    assert table_counts(lab_db) == before
