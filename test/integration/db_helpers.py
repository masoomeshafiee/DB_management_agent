"""Paths and SQL helpers shared by the integration tests."""

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DB = REPO_ROOT / "data" / "sample_data.db"
INSERTION_FIXTURES = REPO_ROOT / "test" / "scenarios" / "insertion"


def count_rows(db_path, sql, params=()):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql, params).fetchone()[0]


def table_counts(db_path, tables=("Experiment", "RawFiles", "Masks", "TrackingFiles")):
    return {table: count_rows(db_path, f"SELECT COUNT(*) FROM {table}") for table in tables}
