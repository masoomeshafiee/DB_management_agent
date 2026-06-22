#!/bin/python3

import logging
from typing import Any, Dict

from google.genai import types

from agent.utils import run_with_backoff

logger = logging.getLogger(__name__)

APPROVAL_WORDS = {"yes", "y", "approve", "approved", "confirm", "ok"}
DENIAL_WORDS = {"no", "n", "deny", "denied", "cancel"}


def parse_confirmation(user_input: str) -> bool | None:
    """Convert explicit CLI approval or denial text into a boolean."""
    value = user_input.strip().lower()

    if value in APPROVAL_WORDS:
        return True
    if value in DENIAL_WORDS:
        return False
    return None


def check_for_approval(events):
    """Check if events contain an approval request.

    Returns:
        dict with approval details or None
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if (
                    part.function_call
                    and part.function_call.name == "adk_request_confirmation"
                ):
                    logger.info(f"APPROVAL REQUEST DETECTED | Tool: {part.function_call.name} | ID: {part.function_call.id}")
                    return {
                        "approval_id": part.function_call.id,
                        "invocation_id": getattr(event, "invocation_id", None),
                    }
    return None


def create_approval_message(
    approval_id: str,
    is_approved: bool,
) -> types.Content:
    """Create a message content for approval response.

    Args:
        approval_id: The ID of the approval request.
        is_approved: Whether the user explicitly approved the operation.

    Returns:
        types.Content object with the approval response.
    """
    confirmation_response = types.FunctionResponse(
        id=approval_id,
        name="adk_request_confirmation",
        response={"confirmed": is_approved},
    )
    return types.Content(
        role="user",
        parts=[types.Part(function_response=confirmation_response)],
    )


async def run_db_workflow(
    runner,
    user_request: str,
    session_id: str,
    user_id: str = "default_user",
) -> Dict[str, Any]:
    """
    Orchestrates the database operation workflow.
    """
    logger.info(
        "WORKFLOW_START: User Request: %s | Session ID: %s | User ID: %s",
        user_request,
        session_id,
        user_id,
    )

    query_content = types.Content(role="user", parts=[types.Part(text=user_request)])

    events = []
    async for event in run_with_backoff(
        runner,
        user_id=user_id,
        session_id=session_id,
        prompt=query_content,
    ):
        events.append(event)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    logger.info(f"Agent > {part.text}")
                    print(f"Agent > {part.text}")
                if part.function_call:
                    logger.warning(f"Tool Call Detected: {part.function_call.name} with args {part.function_call.args}")

    # check for approval request in the events.
    approval_info = check_for_approval(events)

    # If approval is requested, pause and wait for user decision.
    if approval_info:
        logger.warning(f"WAITING_FOR_APPROVAL | ID {approval_info['approval_id']} | Invocation: {approval_info['invocation_id']}")
        print(f"Pausing for approval...")

        while True:
            user_input = input(
                ">> Do you approve the operation? "
                "Type APPROVE to proceed or DENY to cancel: "
            )
            is_approved = parse_confirmation(user_input)
            if is_approved is not None:
                break
            print("Please enter APPROVE or DENY.")

        logger.info(
            "User confirmation interpreted as %s",
            "APPROVE" if is_approved else "DENY",
        )
        approval_message = create_approval_message(
            approval_info["approval_id"],
            is_approved,
        )

        # Resume the paused invocation with the CLI user's decision.
        async for event in run_with_backoff(
            runner,
            user_id=user_id,
            session_id=session_id,
            prompt=approval_message,
            invocation_id=approval_info["invocation_id"],
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")

        logger.info(
            "WORKFLOW_END: Status: completed_with_approval | Approved: %s",
            is_approved,
        )
        return {
            "status": (
                "completed_approved"
                if is_approved
                else "completed_denied"
            )
        }

    logger.info("WORKFLOW_END: Status: completed_without_approval")
    return {"status": "completed_without_approval"}
