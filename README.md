# Database Management Agent

An LLM-powered, agent-based database management system designed to help non-technical biologists interact safely and effectively with a laboratory SQLite database using natural language.

This project uses Google's Agent Development Kit (ADK) to translate human-language requests into validated, auditable database operations, without requiring SQL knowledge, lowering the barrier to good data management practices in experimental biology labs.

**Status:** Active development. This repository contains Version 1, focused on correctness, safety, and observability.

Contributors: Masoumeh Shafiei, Niusha Mirhakimi.

---

#### **Problem Motivation**

Many biology labs rely on relational databases (often SQLite) to store experimental metadata, yet:
- Most users do not know SQL
- Direct database access increases the risk of accidental data loss
- Validation, auditing, and reproducibility are often missing or ad hoc

This project addresses these challenges by introducing an agent-based intermediary that:
- Accepts natural language requests
- Routes tasks to specialized agents
- Executes predefined, safe Python query builders — never free-form, LLM-generated SQL
- Logs every action for traceability and recovery

#### **Core Objective**

To build an LLM-powered database manager that enables non-technical users to:
- Search records
- Insert validated data (from CSV)
- Delete records with explicit, human-in-the-loop confirmation
- Maintain traceable, auditable database interactions

All without writing SQL.

---

#### **High-Level Architecture**

```
User
 ├─ Web path:  Streamlit UI (ui/app.py)
 │               ↓ HTTP (requests)
 │             FastAPI backend (server.py)
 │               ↓ await
 └─ CLI path:  main.py
                ↓ direct import
              workflow.py  (submit_request · resume_with_confirmation)
                ↓
              ADK root_agent
                ↓ transfer_to_agent (LLM-routed)
        ┌───────┼──────────────────┐
   query_agent  insert_supervisor_agent  delete_supervisor_agent
        │              │                        │
        │       (validate → insert)      (extract filters → preview → confirm → delete)
        ↓              ↓                        ↓
              Python query builders (lab_data_manager)
                        ↓
                  SQLite database
```

Two ways to talk to the same agent stack: a CLI (`main.py`) for local/scripted use, and a web path (Streamlit → FastAPI) for interactive use. Both call the exact same `workflow.py` functions — the agent logic itself has no notion of which frontend is driving it.

**Root Agent** is a pure traffic controller: it only decides which specialist agent should handle a request (`transfer_to_agent`) and never touches the database itself.

**Important design constraints:**

1. **No free-form SQL generation.** Agents call explicit, tested Python query-builder functions (from the separate `lab_data_manager` package) rather than writing SQL themselves. This prevents hallucinated or unsafe SQL and keeps behavior testable.

2. **The Python database layer is a separate repository.** The code that directly interfaces with the SQLite database — and whose functions are exposed to the agents as tools — is developed and maintained here:
   https://github.com/masoomeshafiee/data-management-system-SQLite
   It must be installed (editable install recommended) alongside this repo.

3. **Deletion is two-step and confirmation-gated.** A `preview_deletion` dry-run computes exactly what would be deleted and stores it in session state; the real `execute_deletion` call is registered with ADK's `require_confirmation=True`, which pauses the agent invocation and surfaces an explicit approval request. `execute_deletion` reads its filters back from the stored preview state — never from a fresh, potentially different, LLM inference — so what you approve is exactly what gets deleted.

---

#### **Agent Design**

| Agent | File | Role |
|---|---|---|
| **Root Agent** | `agent/root_agent.py` | Routes each request to the right specialist agent. Never touches the database directly. |
| **Query Agent** | `agent/query_agent.py` | Answers search/count/trend/data-quality questions via read-only query-builder tools. |
| **Filter Agent** | `agent/filter_agent.py` | Extracts a structured `{table, filters, limit}` request from natural language for deletion. |
| **Delete Agent** | `agent/delete_agent.py` | Calls `preview_deletion` (dry run), then `execute_deletion` once ADK's confirmation gate is satisfied. |
| **Delete Supervisor** | `agent/delete_supervisor_agent.py` | `SequentialAgent`: Filter Agent → Delete Agent. |
| **Data Validation Agent** | `agent/data_validation_agent.py` | Validates a CSV against the schema before any insertion happens. |
| **Insert Agent** | `agent/insert_agent.py` | Performs the actual insert once validation has passed. |
| **Insert Supervisor** | `agent/insert_supervisor_agent.py` | `SequentialAgent`: Data Validation Agent → Insert Agent. Returns skipped/rejected rows alongside inserted ones. |

`agent/pydantic_models.py` holds the shared filter schema (`LabFilters`/`StrictLabFilters`/`DeletionSchema`) that both the query and delete paths validate against, `agent/utils.py` holds the deterministic helpers (table-name resolution, deletion state management, filter sanitization), and `agent/config.py` loads `.env` and holds the shared Gemini retry configuration.

---

#### **Features**

**Natural Language Interface:**
Users express requests in plain English, for instance:
- "Show all experiments from yeast cells in January"
- "Insert this metadata CSV"
- "Delete all the invalid experiments from last week"

**Multi-Agent Task Decomposition:** requests are routed to specialized agents (search, filter, validate, insert, delete-with-confirmation) rather than one monolithic prompt trying to do everything.

**Safe Database Operations:**
- No raw SQL exposed to (or generated by) the LLM
- Parameterized Python query builders only
- Schema validation enforced before insertion
- Human approval required before any deletion executes

**Persistent Session Management:**
- Sessions are backed by ADK's `DatabaseSessionService` (SQLite-backed), not in-memory — a session survives a process restart
- Sessions can be named and resumed, from both the CLI and the Streamlit UI

**Observability & Auditing:**
Logging is centralized in `observability/logging_config.py` and split by concern, each file rotating so nothing grows unbounded:
- `logs/audit.log` — one line per request, tool call, approval decision, and final response: a clean, complete audit trail of every interaction
- `logs/app.log` — general application logs
- `logs/adk.log` — ADK/Gemini framework-level tracing
- `logs/error.log` — every warning and error, including unhandled exceptions from the FastAPI server itself

---

#### **Input & Output Examples**

##### Example 1 — Search:

**User input**
```
Find all experiments with organism yeast and protein Rfa1 that are untreated and invalid.
```
**Agent output** — a formatted table of matching records, e.g.:
```
Here are 11 experiments matching your criteria:
| id | organism | protein | strain | condition | ... | is_valid | ... |
| 25 | yeast    | rfa1    | zey098 | untreated | ... | N        | ... |
...
```

##### Example 2 — Insert (CSV)

**User input**
```
Insert the records from metadata_run_12.csv
```
**Agent behavior**
- Validates schema and field formats
- Rejects invalid rows, inserts only validated ones
- Reports how many rows were inserted vs. skipped, and why

##### Example 3 — Delete (human-in-the-loop)

**User input**
```
Delete all invalid experiments from March.
```
**Preview (before any confirmation)** — shown to the user before anything is touched:
```
This will delete 18 record(s) from 'Experiment' matching filters: {"date": "202303...", "is_valid": "N"}
Preview saved to: data/deletion_previews/delete_preview_<timestamp>.csv
```
Deletion proceeds only after the user explicitly approves or denies this specific preview.

---

#### **Project Structure**

```
DB_management_agent/
├── agent/
│   ├── root_agent.py
│   ├── query_agent.py
│   ├── filter_agent.py
│   ├── delete_agent.py
│   ├── delete_supervisor_agent.py
│   ├── data_validation_agent.py
│   ├── insert_agent.py
│   ├── insert_supervisor_agent.py
│   ├── pydantic_models.py
│   ├── utils.py
│   └── config.py
├── observability/
│   └── logging_config.py
├── ui/
│   └── app.py            # Streamlit frontend
├── test/
│   └── unit/              # pytest unit tests
├── workflow.py             # submit_request() / resume_with_confirmation()
├── main.py                 # CLI entrypoint
├── server.py                # FastAPI backend (/session /chat /confirm /cancel)
├── requirements.txt
├── .env.example
└── README.md
```

---

#### **Technologies Used**
- Python
- SQLite
- Google Agent Development Kit (ADK) + Gemini
- FastAPI
- Streamlit

---

#### **Getting Started**

**Prerequisites**
- Python ≥ 3.10
- A Google AI Studio API key (`GOOGLE_API_KEY`)
- The `lab_data_manager` package installed from the [companion repo](https://github.com/masoomeshafiee/data-management-system-SQLite)

**Installation**
```bash
git clone https://github.com/masoomeshafiee/DB_management_agent.git
cd DB_management_agent
pip install -r requirements.txt
```

**Configuration**
```bash
cp .env.example .env
# then edit .env and set GOOGLE_API_KEY=<your key>
```

**Usage — three ways to run it:**

```bash
# CLI
python main.py

# FastAPI backend
uvicorn server:app --reload

# Streamlit UI (needs the FastAPI backend running too)
streamlit run ui/app.py
```

**Tests**
```bash
pytest test/unit/ -v
```

Example CLI interaction:
```
Enter your database request: Show all experiments from E.coli with protein DnaA.
Agent Response> Found 24 matching records.
```

#### Contributors
- **Masoumeh Shafiei**
- **Niusha Mirhakimi**
