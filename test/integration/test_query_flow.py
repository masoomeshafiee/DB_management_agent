"""Integration tests for the search tools against a real SQLite copy."""

import pytest

from agent.query_agent import count_experiments_by_group, search_experiments

pytestmark = pytest.mark.integration


def test_search_returns_matching_experiments(lab_db):
    text = search_experiments({"organism": "yeast"}, db_path=lab_db, limit=5)
    assert "yeast" in text
    assert "Total records: 5" in text


def test_is_valid_false_finds_the_invalid_experiments(lab_db):
    text = search_experiments({"is_valid": False}, db_path=lab_db, limit=50)
    assert "Total records: 14" in text


def test_unknown_filter_returns_an_error_instead_of_querying(lab_db):
    assert search_experiments({"colour": "blue"}, db_path=lab_db).startswith("Invalid filter fields")


def test_no_matches_says_so(lab_db):
    text = search_experiments({"organism": "zebrafish"}, db_path=lab_db)
    assert text == "No records matched the given criteria."


def test_counting_by_group_reports_every_group(lab_db):
    text = count_experiments_by_group(["is_valid"], db_path=lab_db)
    assert "14" in text and "49" in text
