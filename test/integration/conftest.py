"""Fixtures for integration tests that run against a real copy of the sample database."""

import shutil

import pytest

from .db_helpers import SAMPLE_DB


@pytest.fixture
def lab_db(tmp_path, monkeypatch):
    """A throwaway copy of sample_data.db.

    lab_data_manager writes deletion previews to ../data/deletion_previews
    relative to the working directory, so the test runs from a temporary
    folder to keep those files out of the repository.
    """
    db_path = tmp_path / "lab.db"
    shutil.copy(SAMPLE_DB, db_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    return str(db_path)
