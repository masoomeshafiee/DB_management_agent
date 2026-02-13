#!/bin/python3

from google.adk.agents import Agent, LlmAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.runners import Runner
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.tools import AgentTool, FunctionTool
from google.genai import types
from google.adk.sessions import InMemorySessionService
import asyncio
import os
from typing import Dict, Any
import uuid
from agent.utils import run_with_backoff

from lab_data_manager import data_validation, insert_csv
from lab_data_manager.insert_csv import insert_from_csv
from lab_data_manager.delete_records import delete_records_by_filter
from google.adk.tools.tool_context import ToolContext
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.apps.app import App, ResumabilityConfig
import logging

logger = logging.getLogger(__name__)
def check_for_approval(events):
    """Check if events contain an approval request.

    Returns:
        dict with approval details or None
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if (part.function_call and
                    part.function_call.name == "adk_request_confirmation"
                ):
                    logger.info(f"APPROVAL REQUEST DETECTED | Tool: {part.function_call.name} | ID: {part.function_call.id}")
                    return {
                        "approval_id": part.function_call.id,
                        "invocation_id": getattr(event, "invocation_id", None),
                    }
    return None

def create_approval_message(approval_id: str, user_input:str) -> types.Content:
    """Create a message content for approval response.

    Args:
        approval_id: The ID of the approval request.
        user_input: User's input text (e.g., "approve" or "deny").

    Returns:
        types.Content object with the approval response.
    """

    #clean input and accept 'yes', 'approve', 'ok', 'yes', 'y' as approval
    cleaned_input = user_input.strip().lower()
    is_approved = cleaned_input in ["yes", "approve", "ok", "y"]

    logger.info(f"User input for approval: '{user_input}' | Interpreted as {'APPROVE' if is_approved else 'DENY'}")
    confirmation_response = types.FunctionResponse(id = approval_id, name = "adk_request_confirmation", response = {"confirmed": is_approved})
    return types.Content(role = "user", parts = [types.Part(function_response = confirmation_response)]), is_approved



async def run_db_workflow(runner, user_request:str, session_id:str, user_id:str="default_user") -> Dict[str, Any]:
    """
    Orchestrates the database operation workflow.
    """
    logger.info(f"WORKFLOW_START: User Request: {user_request}| Session ID: {session_id} | User ID: {user_id}")

    query_content = types.Content(role="user", parts=[types.Part(text=user_request)])
    
    events = []
    async for event in run_with_backoff(runner, user_id= user_id, session_id = session_id, prompt = query_content):
        events.append(event)
        #print thoughts as they happen
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
        user_input = input(">> Do you approve the operation? Type APPROVE to proceed or DENY to cancel: ")
        
        #create approval message
        approval_message, is_approved  = create_approval_message(approval_info["approval_id"], user_input)

        #resume the runner with the approval message
        async for event in run_with_backoff(
            runner,
            user_id=user_id,
            session_id=session_id,
            prompt =approval_message,
            invocation_id=approval_info["invocation_id"]
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")

            logger.info(f"WORKFLOW_END: Status: completed_with_approval | Approved: {is_approved}")
        return {"status": "completed__approved" if is_approved else "completed_denied"}
    logger.info(f"WORKFLOW_END: Status: completed_without_approval")    
    return {"status": "completed_without_approval"}

    