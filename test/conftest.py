"""Shared pytest fixtures for the database manager test suite."""

from types import SimpleNamespace

import pytest
from google.genai import types

import agent.utils as utils


def build_tool_context(user_text="delete invalid tracking files", confirmed=None, state=None):
    """A stand-in for ADK's ToolContext with only the attributes our tools read.

    SimpleNamespace instead of MagicMock on purpose: a MagicMock invents any
    attribute it is asked for, so a missing `tool_confirmation` would look
    like an approval and safety tests would pass for the wrong reason.
    """
    content = types.Content(role="user", parts=[types.Part(text=user_text)])
    ctx = SimpleNamespace(
        state=dict(state or {}),
        _invocation_context=SimpleNamespace(user_content=content),
    )
    if confirmed is not None:
        ctx.tool_confirmation = SimpleNamespace(confirmed=confirmed)
    return ctx


@pytest.fixture
def make_tool_context():
    return build_tool_context


class FakeDeleteRecords:
    """Replaces lab_data_manager's delete_records_by_filter and records every call."""

    def __init__(self):
        self.calls = []
        self.preview_count = 3
        self.error = None
        self.execute_result = None

    def __call__(self, db_path, table, filters, limit, dry_run):
        self.calls.append(
            {"db_path": db_path, "table": table, "filters": filters, "limit": limit, "dry_run": dry_run}
        )
        if self.error:
            raise self.error
        if dry_run:
            return {"preview_count": self.preview_count, "preview_path": "/tmp/preview.csv"}
        if self.execute_result is not None:
            return self.execute_result
        return {"deleted": self.preview_count}


@pytest.fixture
def fake_delete(monkeypatch):
    fake = FakeDeleteRecords()
    # Patch the name where utils looks it up, not where it is defined.
    monkeypatch.setattr(utils, "delete_records_by_filter", fake)
    return fake
