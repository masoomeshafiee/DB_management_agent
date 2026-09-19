# from agent.root_agent import db_manager_app
# from google.adk.apps.web import WebApp

# # This is the "hook" the web UI needs
# app = WebApp(db_manager_app)

# if __name__ == "__main__":
#     app.run()


from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.errors.already_exists_error import AlreadyExistsError

from agent.root_agent import db_manager_app
from workflow import submit_request, resume_with_confirmation, parse_confirmation
from observability.logging_config import config_logging


DB_FOLDER = "db_manager_app_state"
DB_FILE = "sessions.db"


class SessionRequest(BaseModel):
    session_name: str
    user_request: str="default_user"


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: str = "default_user"


class ConfirmationRequest(BaseModel):
    session_id: str
    approval_id: str
    invocation_id: str
    user_id: str = "default_user"

   
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    config_logging(level="INFO")
    session_service = DatabaseSessionService(f"sqlite:///{DB_FOLDER}/{DB_FILE}")
    runner = Runner(session_service=session_service, app=db_manager_app)
    yield {"session_service": session_service, "runner": runner}


app = FastAPI(lifespan=lifespan)


@app.post("/session")
async def create_session(body: SessionRequest, request: Request):
    """Create a new session."""
    session_service: DatabaseSessionService = request.state.session_service
    try:
        await session_service.create_session(
            app_name=db_manager_app.name,
            user_id="default_user",
            session_id=body.session_name
        )
        return {"message": f"Session '{body.session_name}' created successfully."}
    except AlreadyExistsError:
        return {"error": f"Session '{body.session_name}' already exists."}


@app.post("/chat")
async def chat(body: ChatRequest, request: Request):
    """Handle chat messages."""
    runner: Runner = request.state.runner
    response = await submit_request(runner, body.message, body.session_id, user_id=body.user_id)

    return response


@app.post("/confirm")
async def confirm(body: ConfirmationRequest, request: Request):
    """Handle confirmation requests."""
    runner: Runner = request.state.runner
    response = await resume_with_confirmation(
        runner,
        approval_id=body.approval_id,
        invocation_id=body.invocation_id,
        is_approved=True,
        session_id=body.session_id,
        user_id=body.user_id
    )
    return response


@app.post("/cancel")
async def cancel(body: ConfirmationRequest, request: Request):
    """Cancel the current operation."""
    runner: Runner = request.state.runner
    response = await resume_with_confirmation(
        runner, body.approval_id, body.invocation_id, is_approved=False,
        session_id=body.session_id, user_id=body.user_id,
    )
    return response