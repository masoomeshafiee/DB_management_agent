"""Unit tests for confirmation parsing, ADK event parsing, and invocation resumption."""

from types import SimpleNamespace

import pytest
from google.genai import types

from workflow import (
    APPROVAL_WORDS,
    DENIAL_WORDS,
    check_for_approval,
    create_approval_message,
    extract_deletion_result,
    extract_insert_result,
    extract_pending_deletion,
    extract_validation_result,
    parse_confirmation,
    resume_with_confirmation,
    submit_request,
)

pytestmark = pytest.mark.unit


# ---------- Fake ADK events ----------

def text_event(text, invocation_id="inv-1"):
    return SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        actions=None,
        invocation_id=invocation_id,
    )


def call_event(name, call_id="call-1", invocation_id="inv-1", state_delta=None):
    call = types.FunctionCall(id=call_id, name=name, args={})
    return SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(function_call=call)]),
        actions=SimpleNamespace(state_delta=state_delta or {}),
        invocation_id=invocation_id,
    )


def response_event(name, response):
    result = types.FunctionResponse(id="call-1", name=name, response=response)
    return SimpleNamespace(
        content=types.Content(role="user", parts=[types.Part(function_response=result)]),
        actions=None,
        invocation_id="inv-1",
    )


def confirmation_event(preview=None):
    return call_event(
        "adk_request_confirmation",
        call_id="appr-1",
        state_delta={"pending_deletion": preview} if preview else {},
    )


# ---------- parse_confirmation ----------

@pytest.mark.parametrize("word", sorted(APPROVAL_WORDS))
def test_every_approval_word_approves(word):
    assert parse_confirmation(word) is True


@pytest.mark.parametrize("word", sorted(DENIAL_WORDS))
def test_every_denial_word_denies(word):
    assert parse_confirmation(word) is False


@pytest.mark.parametrize("text", ["  APPROVE ", "Yes", "CANCEL"])
def test_parsing_ignores_case_and_spaces(text):
    assert parse_confirmation(text) is not None


@pytest.mark.parametrize("text", ["", "maybe", "yes please"])
def test_anything_else_is_neither_approval_nor_denial(text):
    assert parse_confirmation(text) is None


# ---------- create_approval_message ----------

@pytest.mark.parametrize("approved", [True, False])
def test_approval_message_carries_the_decision(approved):
    message = create_approval_message("appr-1", approved)
    response = message.parts[0].function_response
    assert message.role == "user"
    assert (response.id, response.name, response.response) == (
        "appr-1",
        "adk_request_confirmation",
        {"confirmed": approved},
    )


# ---------- check_for_approval ----------

def test_approval_request_is_found():
    events = [text_event("26 records would be deleted."), confirmation_event()]
    assert check_for_approval(events) == {"approval_id": "appr-1", "invocation_id": "inv-1"}


def test_text_asking_for_permission_is_not_an_approval_request():
    assert check_for_approval([text_event("Should I proceed with the deletion?")]) is None


def test_other_tool_calls_are_not_approval_requests():
    assert check_for_approval([call_event("preview_deletion")]) is None


def test_events_without_content_are_skipped():
    assert check_for_approval([SimpleNamespace(content=None, actions=None)]) is None


# ---------- extract_pending_deletion / extract_insert_result ----------

def test_preview_is_read_from_the_state_change():
    preview = {"table": "Masks", "preview_count": 26}
    assert extract_pending_deletion([text_event("hi"), confirmation_event(preview)]) == preview


def test_no_preview_when_nothing_was_previewed():
    assert extract_pending_deletion([text_event("Found 3 experiments.")]) is None


def test_insert_result_is_read_from_the_state_change():
    summary = {"inserted_count": 2, "skipped_count": 1}
    event = call_event("insert_csv_with_report", state_delta={"last_insert_result": summary})
    assert extract_insert_result([event]) == summary


# ---------- extract_validation_result ----------

def validation_events(output_path, result):
    """The call the validation agent makes, then the value the validator returned."""
    call = types.FunctionCall(
        id="val-1", name="validate_csv", args={"file_path": "upload.csv", "output_path": str(output_path)}
    )
    response = types.FunctionResponse(id="val-1", name="validate_csv", response={"result": result})
    return [
        SimpleNamespace(content=types.Content(role="model", parts=[types.Part(function_call=call)]), actions=None),
        SimpleNamespace(content=types.Content(role="user", parts=[types.Part(function_response=response)]), actions=None),
    ]


@pytest.fixture
def invalid_rows_file(tmp_path):
    path = tmp_path / "invalid_rows.csv"
    path.write_text("file_name,row_number,issues\n,455,Filename error\n")
    return path


# The library returns the invalid rows; a local variant returns their count.
@pytest.mark.parametrize("result", [[{"row_number": 455}], 1])
def test_failed_validation_returns_the_rows_from_the_file_the_tool_wrote(invalid_rows_file, result):
    found = extract_validation_result(validation_events(invalid_rows_file, result))

    assert found["output_path"] == str(invalid_rows_file)
    assert found["invalid_rows"] == [{"file_name": "", "row_number": "455", "issues": "Filename error"}]


@pytest.mark.parametrize("result", [[], 0])
def test_passed_validation_reports_nothing_even_if_an_old_file_exists(invalid_rows_file, result):
    assert extract_validation_result(validation_events(invalid_rows_file, result)) is None


def test_no_validation_result_when_no_file_was_validated():
    assert extract_validation_result([text_event("Found 3 experiments.")]) is None


# ---------- extract_deletion_result ----------

def test_deletion_result_is_read_from_the_tool_response():
    outcome = {"status": "completed", "deleted_count": 26}
    events = [response_event("execute_deletion", outcome), text_event("Deleted 26 records.")]
    assert extract_deletion_result(events) == outcome


def test_other_tool_responses_are_not_deletion_results():
    assert extract_deletion_result([response_event("preview_deletion", {"status": "preview"})]) is None


# ---------- Async examples: submit_request / resume_with_confirmation ----------
#
# submit_request and resume_with_confirmation receive a runner instead of
# creating one, so a test can hand them a fake whose run_async yields
# whatever events we script. The real Gemini model never runs.

class FakeRunner:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def run_async(self, **kwargs):
        self.calls.append(kwargs)
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_submit_request_pauses_when_the_agent_asks_for_approval():
    preview = {"table": "Masks", "preview_count": 26}
    runner = FakeRunner([text_event("26 records would be deleted."), confirmation_event(preview)])

    result = await submit_request(runner, "delete invalid masks", session_id="s1")

    assert result["status"] == "pending_approval"
    assert result["approval_info"] == {"approval_id": "appr-1", "invocation_id": "inv-1"}
    assert result["preview"] == preview


@pytest.mark.asyncio
async def test_submit_request_completes_a_plain_query():
    runner = FakeRunner([text_event("Found 3 experiments.")])

    result = await submit_request(runner, "list yeast experiments", session_id="s1")

    assert result["status"] == "completed_without_approval"
    assert result["text"] == "Found 3 experiments."
    assert runner.calls[0]["session_id"] == "s1"
    assert runner.calls[0]["new_message"].parts[0].text == "list yeast experiments"


@pytest.mark.asyncio
@pytest.mark.parametrize("approved, expected_status", [
    (True, "completed_approved"),
    (False, "completed_denied"),
])
async def test_resume_sends_the_decision_to_the_same_paused_run(approved, expected_status):
    runner = FakeRunner([text_event("Done.")])

    result = await resume_with_confirmation(
        runner, approval_id="appr-1", invocation_id="inv-1", is_approved=approved, session_id="s1"
    )

    call = runner.calls[0]
    assert call["invocation_id"] == "inv-1"
    assert call["new_message"].parts[0].function_response.response == {"confirmed": approved}
    assert result["status"] == expected_status


@pytest.mark.asyncio
async def test_resume_reports_the_count_the_tool_returned_not_the_model_text():
    outcome = {"status": "completed", "deleted_count": 26}
    runner = FakeRunner([response_event("execute_deletion", outcome), text_event("All done!")])

    result = await resume_with_confirmation(
        runner, approval_id="appr-1", invocation_id="inv-1", is_approved=True, session_id="s1"
    )

    assert result["deletion_result"] == outcome
