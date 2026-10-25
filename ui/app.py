import os
import time

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000"

# run_with_backoff sleeps 65 s on each Gemini rate-limit error and retries up
# to 3 times, so a slow request can legitimately take a few minutes.
BACKEND_TIMEOUT = 240

# Where uploaded CSVs are saved before being handed to the agent as a path.
# The backend (FastAPI/agent) must be able to read this same path, so this
# only works when Streamlit and the backend share a filesystem — true for the
# local/dev setup this app targets.
UPLOAD_DIR = "uploads"
DEFAULT_DB_PATH = os.path.join("data", "sample_data.db")

st.set_page_config(page_title="DB Management Agent", page_icon="🧬")
st.title("DB Management Agent")


# ---------------------------------------------------------------------------
# Session state — everything here must survive a rerun (Streamlit reruns the
# whole script top-to-bottom on every interaction, including button clicks).
# ---------------------------------------------------------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = None  # not started until the user names one
if "messages" not in st.session_state:
    # Each message: {role, content, preview, approval_info, resolved, insert_result, deletion_result}
    # preview/approval_info are only set on the assistant message that just
    # triggered a pending deletion; resolved=False is what makes the
    # confirm/cancel buttons render under that specific message.
    # insert_result is only set on the assistant message that just ran an
    # insertion — it's what makes the results table render under it.
    # deletion_result is only set on the reply to a confirm/cancel click.
    # validation_result is only set on the reply to an uploaded file that
    # failed validation — it's what makes the invalid-rows table render.
    st.session_state.messages = []


def start_session(name: str) -> None:
    session_name = name.strip() or "default"
    try:
        resp = requests.post(
            f"{API_BASE_URL}/session",
            json={"session_name": session_name},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            st.sidebar.info(f"Resuming existing session '{session_name}'.")
        else:
            st.sidebar.success(f"Started new session '{session_name}'.")
    except requests.RequestException as e:
        st.sidebar.error(f"Could not reach the backend at {API_BASE_URL}: {e}")
        return
    st.session_state.session_id = session_name
    st.session_state.messages = []


def call_backend(method_path: str, payload: dict, spinner_text: str = "Working on it…") -> dict:
    """POST to the backend. The result has ok=False if the request itself failed."""
    try:
        with st.spinner(spinner_text):
            resp = requests.post(f"{API_BASE_URL}{method_path}", json=payload, timeout=BACKEND_TIMEOUT)
        resp.raise_for_status()
        return {**resp.json(), "ok": True}
    except requests.RequestException as e:
        return {"ok": False, "text": f"Error contacting backend: {e}", "approval_info": None, "preview": None}


def submit_chat_message(message: str) -> None:
    """Send a message as if typed into the chat box; appends both sides to history."""
    st.session_state.messages.append(
        {
            "role": "user",
            "content": message,
            "preview": None,
            "approval_info": None,
            "resolved": True,
            "insert_result": None,
        }
    )
    result = call_backend("/chat", {"session_id": st.session_state.session_id, "message": message})
    approval_info = result.get("approval_info")
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("text", ""),
            "preview": result.get("preview"),
            "approval_info": approval_info,
            "resolved": approval_info is None,
            "insert_result": result.get("insert_result"),
        }
    )


def handle_insert_upload(uploaded_file, db_path: str, invalid_output_path: str) -> None:
    """Save the uploaded CSV to disk and submit an insert request for it."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    save_path = os.path.abspath(os.path.join(UPLOAD_DIR, uploaded_file.name))
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Absolute, so the backend writes the file where this process will look.
    invalid_output_path = os.path.abspath(invalid_output_path)
    message = (
        f"Insert the data from the CSV file located at {save_path} into the "
        f"database at {db_path}. Save any invalid records found during "
        f"validation to {invalid_output_path}, and return any skipped/invalid rows."
    )
    submitted_at = time.time()
    submit_chat_message(message)
    st.session_state.messages[-1]["validation_result"] = read_validation_failures(
        invalid_output_path, submitted_at
    )
    st.rerun()


def read_validation_failures(output_path: str, since: float) -> dict | None:
    """The invalid rows the validator wrote during this request, if any.

    lab_data_manager only writes output_path when it finds invalid rows, so a
    file modified after the request started means validation failed. The rows
    are copied into the message because the file is overwritten next time.
    """
    if not os.path.exists(output_path) or os.path.getmtime(output_path) < since:
        return None
    try:
        rows = pd.read_csv(output_path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None
    return {"output_path": output_path, "invalid_rows": rows.to_dict("records")}


with st.sidebar:
    st.subheader("Session")
    if st.session_state.session_id:
        st.write(f"Active session: **{st.session_state.session_id}**")
        if st.button("Switch session"):
            st.session_state.session_id = None
            st.session_state.messages = []
            st.rerun()
    else:
        name_input = st.text_input("Session name (leave empty for 'default')")
        if st.button("Start / resume session"):
            start_session(name_input)
            st.rerun()

    if st.session_state.session_id:
        st.divider()
        st.subheader("Insert new data")
        st.caption("Upload a metadata CSV instead of typing its file path.")
        uploaded_file = st.file_uploader("CSV file", type=["csv"])
        db_path = st.text_input("Database file path", value=DEFAULT_DB_PATH)
        invalid_output_path = st.text_input(
            "Invalid-rows output path",
            value=os.path.join("data", "invalid_rows.csv"),
        )
        if st.button("Insert file", disabled=uploaded_file is None):
            handle_insert_upload(uploaded_file, db_path, invalid_output_path)

if not st.session_state.session_id:
    st.info("Enter a session name in the sidebar to begin.")
    st.stop()


def handle_confirmation(msg: dict, approve: bool) -> None:
    approval_info = msg["approval_info"]
    endpoint = "/confirm" if approve else "/cancel"
    result = call_backend(
        endpoint,
        {
            "session_id": st.session_state.session_id,
            "approval_id": approval_info["approval_id"],
            "invocation_id": approval_info["invocation_id"],
        },
        spinner_text="Deleting records…" if approve else "Cancelling…",
    )
    # Only hide the buttons once the backend has the decision. If the request
    # failed, the deletion is still pending, so the user must be able to retry.
    if result["ok"]:
        msg["resolved"] = True
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("text", ""),
            "preview": None,
            "approval_info": None,
            "resolved": True,
            "insert_result": None,
            "deletion_result": result.get("deletion_result"),
        }
    )
    st.rerun()


def load_preview_rows(preview_path: str | None) -> pd.DataFrame | None:
    """Read the dry-run CSV written by preview_deletion, if it is reachable."""
    if not preview_path or not os.path.exists(preview_path):
        return None
    try:
        return pd.read_csv(preview_path)
    except (OSError, pd.errors.ParserError):
        return None


def render_confirmation(msg: dict, idx: int) -> None:
    preview = msg["preview"]
    with st.container(border=True):
        st.warning("⚠️ Confirm Deletion")
        if preview:
            st.write(f"**Table:** {preview['table']}")
            st.write(f"**Filters:** {preview['filters']}")
            if preview.get("limit"):
                st.write(f"**Limit:** {preview['limit']}")
            st.write(f"**{preview['preview_count']} record(s)** will be deleted.")

            rows = load_preview_rows(preview.get("preview_path"))
            if rows is not None:
                st.caption("These are the exact rows that will be removed:")
                st.dataframe(rows, use_container_width=True, height=min(400, 38 + 35 * len(rows)))
                st.download_button(
                    "Download preview as CSV",
                    data=rows.to_csv(index=False),
                    file_name="deletion_preview.csv",
                    mime="text/csv",
                    key=f"download_preview_{idx}",
                )
            else:
                st.caption("Row preview unavailable — the preview file could not be read.")

        count = preview["preview_count"] if preview else ""
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Delete {count} records", key=f"confirm_{idx}", type="primary"):
                handle_confirmation(msg, approve=True)
        with col2:
            if st.button("Cancel", key=f"cancel_{idx}"):
                handle_confirmation(msg, approve=False)


def render_insert_result(insert_result: dict, idx: int) -> None:
    """Counts + a skipped-rows table (with reasons) for a completed insertion."""
    with st.container(border=True):
        total = insert_result.get("total_rows", 0)
        inserted = insert_result.get("inserted_count", 0)
        skipped_rows = insert_result.get("skipped_rows") or []

        col1, col2, col3 = st.columns(3)
        col1.metric("Rows processed", total)
        col2.metric("Inserted", inserted)
        col3.metric("Skipped", len(skipped_rows))

        if skipped_rows:
            st.warning(f"⚠️ {len(skipped_rows)} row(s) were skipped — see reasons below.")
            skipped_df = pd.DataFrame(skipped_rows)
            st.dataframe(skipped_df, use_container_width=True)
            st.download_button(
                "Download skipped rows as CSV",
                data=skipped_df.to_csv(index=False),
                file_name="skipped_rows.csv",
                mime="text/csv",
                key=f"download_skipped_{idx}",
            )
        else:
            st.success("✅ All rows were inserted successfully.")


def render_validation_result(validation_result: dict, idx: int) -> None:
    """Which rows failed validation and why. Nothing is inserted in that case."""
    invalid_df = pd.DataFrame(validation_result["invalid_rows"])
    with st.container(border=True):
        st.error(f"⛔ {len(invalid_df)} row(s) failed validation, so nothing was inserted.")

        # Put the row number and the reason first: those are what the user fixes.
        # row_number counts data rows; +1 for the header gives the row Excel shows.
        if "row_number" in invalid_df.columns:
            invalid_df["row_number"] = pd.to_numeric(invalid_df["row_number"]) + 1
            invalid_df = invalid_df.rename(columns={"row_number": "excel_row"})
        leading = [c for c in ("excel_row", "issues", "file_name") if c in invalid_df.columns]
        invalid_df = invalid_df[leading + [c for c in invalid_df.columns if c not in leading]]
        st.dataframe(invalid_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download invalid rows as CSV",
            data=invalid_df.to_csv(index=False),
            file_name="invalid_rows.csv",
            mime="text/csv",
            key=f"download_invalid_{idx}",
        )


def render_deletion_result(deletion_result: dict) -> None:
    """The outcome reported by execute_deletion itself, not the model's wording."""
    status = deletion_result.get("status")
    if status == "completed":
        st.success(f"✅ Deleted {deletion_result.get('deleted_count', 0)} record(s).")
    elif status == "cancelled":
        st.info("Deletion cancelled. No records were removed.")
    else:
        st.error(deletion_result.get("message", "Deletion failed."))


# ---------------------------------------------------------------------------
# Render the conversation so far
# ---------------------------------------------------------------------------

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("approval_info") and not msg.get("resolved"):
            render_confirmation(msg, i)
        if msg.get("insert_result"):
            render_insert_result(msg["insert_result"], i)
        if msg.get("deletion_result"):
            render_deletion_result(msg["deletion_result"])
        if msg.get("validation_result"):
            render_validation_result(msg["validation_result"], i)

# ---------------------------------------------------------------------------
# New message input
# ---------------------------------------------------------------------------

user_input = st.chat_input("Enter your database request...")
if user_input:
    submit_chat_message(user_input)
    st.rerun()
