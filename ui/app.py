import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="DB Management Agent", page_icon="🧬")
st.title("DB Management Agent")


# ---------------------------------------------------------------------------
# Session state — everything here must survive a rerun (Streamlit reruns the
# whole script top-to-bottom on every interaction, including button clicks).
# ---------------------------------------------------------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = None  # not started until the user names one
if "messages" not in st.session_state:
    # Each message: {role, content, preview, approval_info, resolved}
    # preview/approval_info are only set on the assistant message that just
    # triggered a pending deletion; resolved=False is what makes the
    # confirm/cancel buttons render under that specific message.
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

if not st.session_state.session_id:
    st.info("Enter a session name in the sidebar to begin.")
    st.stop()


def call_backend(method_path: str, payload: dict) -> dict:
    try:
        resp = requests.post(f"{API_BASE_URL}{method_path}", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"text": f"Error contacting backend: {e}", "approval_info": None, "preview": None}


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


# ---------------------------------------------------------------------------
# Render the conversation so far
# ---------------------------------------------------------------------------

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("approval_info") and not msg.get("resolved"):
            render_confirmation(msg, i)

# ---------------------------------------------------------------------------
# New message input
# ---------------------------------------------------------------------------

user_input = st.chat_input("Enter your database request...")
if user_input:
    st.session_state.messages.append(
        {"role": "user", "content": user_input, "preview": None, "approval_info": None, "resolved": True}
    )

    result = call_backend("/chat", {"session_id": st.session_state.session_id, "message": user_input})
    approval_info = result.get("approval_info")
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.get("text", ""),
            "preview": result.get("preview"),
            "approval_info": approval_info,
            "resolved": approval_info is None,
        }
    )
    st.rerun()
