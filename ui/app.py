import os

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000"

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
    # Each message: {role, content, preview, approval_info, resolved, insert_result}
    # preview/approval_info are only set on the assistant message that just
    # triggered a pending deletion; resolved=False is what makes the
    # confirm/cancel buttons render under that specific message.
    # insert_result is only set on the assistant message that just ran an
    # insertion — it's what makes the results table render under it.
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


def call_backend(method_path: str, payload: dict) -> dict:
    try:
        resp = requests.post(f"{API_BASE_URL}{method_path}", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"text": f"Error contacting backend: {e}", "approval_info": None, "preview": None}


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

    message = (
        f"Insert the data from the CSV file located at {save_path} into the "
        f"database at {db_path}. Save any invalid records found during "
        f"validation to {invalid_output_path}, and return any skipped/invalid rows."
    )
    submit_chat_message(message)
    st.rerun()


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
    )
    msg["resolved"] = True  # hides this message's buttons on the next rerun
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("text", ""),
            "preview": None,
            "approval_info": None,
            "resolved": True,
            "insert_result": None,
        }
    )
    st.rerun()


def render_confirmation(msg: dict, idx: int) -> None:
    preview = msg["preview"]
    with st.container(border=True):
        st.warning("⚠️ Confirm Deletion")
        if preview:
            st.write(f"**Table:** {preview['table']}")
            st.write(f"**Filters:** {preview['filters']}")
            st.write(f"**{preview['preview_count']} record(s)** will be deleted.")

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

# ---------------------------------------------------------------------------
# New message input
# ---------------------------------------------------------------------------

user_input = st.chat_input("Enter your database request...")
if user_input:
    submit_chat_message(user_input)
    st.rerun()
