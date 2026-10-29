import os
"""Unit tests for the CSV insert wrapper's guards and result reporting."""

import pytest

import agent.utils as utils

pytestmark = pytest.mark.unit


class FakeInsert:
    def __init__(self, skipped_rows=None, error=None):
        self.calls = []
        self.skipped_rows = skipped_rows or []
        self.error = error

    def __call__(self, csv_path, db_path, skipped_rows):
        self.calls.append((csv_path, db_path))
        if self.error:
            raise self.error
        return list(self.skipped_rows)


@pytest.fixture
def fake_insert(monkeypatch):
    fake = FakeInsert()
    monkeypatch.setattr(utils, "insert_from_csv", fake)
    return fake


@pytest.fixture
def files(tmp_path):
    csv_path = tmp_path / "metadata.csv"
    csv_path.write_text("organism,protein\nyeast,Rfa1\nyeast,Rad52\nmouse,Rfa1\n,\n")
    db_path = tmp_path / "lab.db"
    db_path.write_bytes(b"")
    return str(csv_path), str(db_path)


def test_missing_csv_path_is_rejected(make_tool_context, fake_insert, files):
    _, db_path = files
    assert utils.insert_csv_with_report(make_tool_context(), csv_path="", db_path=db_path)["status"] == "error"
    assert fake_insert.calls == []


def test_same_file_as_csv_and_database_is_rejected(make_tool_context, fake_insert, files):
    csv_path, _ = files
    result = utils.insert_csv_with_report(make_tool_context(), csv_path=csv_path, db_path=csv_path)
    assert result["status"] == "error"
    assert fake_insert.calls == []


def test_missing_csv_file_is_rejected(make_tool_context, fake_insert, files, tmp_path):
    _, db_path = files
    result = utils.insert_csv_with_report(make_tool_context(), csv_path=str(tmp_path / "nope.csv"), db_path=db_path)
    assert result["status"] == "error"
    assert fake_insert.calls == []


def test_missing_database_file_is_rejected(make_tool_context, fake_insert, files, tmp_path):
    csv_path, _ = files
    result = utils.insert_csv_with_report(make_tool_context(), csv_path=csv_path, db_path=str(tmp_path / "nope.db"))
    assert result["status"] == "error"
    assert fake_insert.calls == []


def test_successful_insert_reports_counts_and_saves_them_for_the_ui(make_tool_context, fake_insert, files):
    csv_path, db_path = files
    fake_insert.skipped_rows = [{"row": 2, "reason": "duplicate"}]
    ctx = make_tool_context()
    utils._record_validation(ctx, csv_path, [])

    result = utils.insert_csv_with_report(ctx, csv_path=csv_path, db_path=db_path)

    assert (result["status"], result["inserted_count"], result["skipped_count"]) == ("completed", 2, 1)
    assert ctx.state["last_insert_result"] == {
        "csv_path": csv_path,
        "db_path": db_path,
        "total_rows": 3,
        "inserted_count": 2,
        "skipped_count": 1,
        "skipped_rows": [{"row": 2, "reason": "duplicate"}],
    }


def test_insert_failure_is_reported_as_an_error(make_tool_context, fake_insert, files):
    csv_path, db_path = files
    fake_insert.error = RuntimeError("database locked")
    ctx = make_tool_context()
    utils._record_validation(ctx, csv_path, [])
    result = utils.insert_csv_with_report(ctx, csv_path=csv_path, db_path=db_path)
    assert result["status"] == "error"
    assert "last_insert_result" not in ctx.state


def test_file_that_failed_validation_is_not_inserted(make_tool_context, fake_insert, files):
    csv_path, db_path = files
    ctx = make_tool_context()
    utils._record_validation(ctx, csv_path, [{"row_number": 3, "issues": ["Invalid organism"]}])
    result = utils.insert_csv_with_report(ctx, csv_path=csv_path, db_path=db_path)
    assert result["status"] == "blocked"
    assert fake_insert.calls == []


def test_file_that_was_never_validated_is_not_inserted(make_tool_context, fake_insert, files):
    csv_path, db_path = files
    result = utils.insert_csv_with_report(make_tool_context(), csv_path=csv_path, db_path=db_path)
    assert result["status"] == "blocked"
    assert fake_insert.calls == []


def test_passing_a_different_file_does_not_unlock_the_insert(make_tool_context, fake_insert, files, tmp_path):
    csv_path, db_path = files
    ctx = make_tool_context()
    utils._record_validation(ctx, str(tmp_path / "other.csv"), [])
    result = utils.insert_csv_with_report(ctx, csv_path=csv_path, db_path=db_path)
    assert result["status"] == "blocked"
    assert fake_insert.calls == []


def test_validation_tool_records_whether_the_file_passed(make_tool_context, monkeypatch, tmp_path):
    ctx = make_tool_context()
    monkeypatch.setattr(utils.data_validation, "validate_csv", lambda file_path, output_path: 2)
    utils.validate_csv("data.csv", str(tmp_path / "invalid.csv"), ctx)
    assert ctx.state["last_validation"] == {"csv_path": os.path.abspath("data.csv"), "passed": False}
