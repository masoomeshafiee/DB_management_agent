"""Integration tests for the FastAPI layer with the agent workflow faked.

The app, its lifespan and its routes are real. The session service, runner,
and workflow functions are replaced, so no model is called and no session
database is created. These check the HTTP contract the Streamlit UI depends on.
"""

import pytest
from fastapi.testclient import TestClient
from google.adk.errors.already_exists_error import AlreadyExistsError

import server

pytestmark = pytest.mark.integration


class FakeSessionService:
    def __init__(self, url):
        self.sessions = set()

    async def create_session(self, app_name, user_id, session_id):
        if session_id in self.sessions:
            raise AlreadyExistsError(f"Session {session_id} already exists")
        self.sessions.add(session_id)


@pytest.fixture
def client(monkeypatch):
    calls = {"submit": [], "resume": []}

    async def fake_submit(runner, message, session_id, user_id="default_user"):
        calls["submit"].append({"message": message, "session_id": session_id})
        return {
            "status": "pending_approval",
            "text": "26 records would be deleted.",
            "approval_info": {"approval_id": "appr-1", "invocation_id": "inv-1"},
            "preview": {"table": "Masks", "preview_count": 26},
            "insert_result": None,
        }

    async def fake_resume(runner, approval_id, invocation_id, is_approved, session_id, user_id="default_user"):
        calls["resume"].append(
            {"approval_id": approval_id, "invocation_id": invocation_id, "is_approved": is_approved}
        )
        return {"status": "completed_approved" if is_approved else "completed_denied", "text": "Done."}

    monkeypatch.setattr(server, "config_logging", lambda level: None)
    monkeypatch.setattr(server, "DatabaseSessionService", FakeSessionService)
    monkeypatch.setattr(server, "Runner", lambda **kwargs: "fake-runner")
    monkeypatch.setattr(server, "submit_request", fake_submit)
    monkeypatch.setattr(server, "resume_with_confirmation", fake_resume)

    with TestClient(server.app) as test_client:
        test_client.calls = calls
        yield test_client


def test_new_session_is_created(client):
    assert "created" in client.post("/session", json={"session_name": "demo"}).json()["message"]


def test_existing_session_is_reported(client):
    client.post("/session", json={"session_name": "demo"})
    assert "already exists" in client.post("/session", json={"session_name": "demo"}).json()["error"]


def test_chat_passes_the_message_through_and_returns_the_approval_ids(client):
    response = client.post("/chat", json={"session_id": "demo", "message": "delete invalid masks"})

    assert response.status_code == 200
    assert response.json()["approval_info"] == {"approval_id": "appr-1", "invocation_id": "inv-1"}
    assert client.calls["submit"] == [{"message": "delete invalid masks", "session_id": "demo"}]


@pytest.mark.parametrize("endpoint, approved", [("/confirm", True), ("/cancel", False)])
def test_confirm_and_cancel_resume_the_paused_run_with_the_right_decision(client, endpoint, approved):
    body = {"session_id": "demo", "approval_id": "appr-1", "invocation_id": "inv-1"}

    response = client.post(endpoint, json=body)

    assert response.status_code == 200
    assert client.calls["resume"] == [{"approval_id": "appr-1", "invocation_id": "inv-1", "is_approved": approved}]


def test_chat_without_a_message_is_rejected(client):
    assert client.post("/chat", json={"session_id": "demo"}).status_code == 422
