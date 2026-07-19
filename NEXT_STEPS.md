# Next Steps for the Database Manager Codebase

## Purpose

This document lists the main areas that still need work in the database manager
project. The goal is to turn the current agent prototype into a more reliable,
testable, and user-friendly database management package.

## Current State

The project already supports a useful first version of a database agent system:

- A root agent routes requests to query, insert, or delete workflows.
- Query tools can inspect and search lab database records.
- Insert tools support CSV-based insertion workflows.
- Delete operations use a safer two-step flow: preview first, then user
  confirmation before execution.
- Pydantic models validate structured deletion requests and filter fields.
- A CLI workflow can run the agents and handle ADK confirmation events.
- A first testing folder structure exists for unit, integration, UI, and
  agent evaluation tests.

## Highest Priority Work

### 1. Stabilize the Deletion Workflow

The deletion flow is the riskiest part of the system because it modifies data.
It should be made very predictable before adding more write operations.

Work needed:

- Keep the two-step behavior: preview before execution.
- Ensure empty filters are always blocked.
- Ensure confirmed execution always uses the saved preview state, not newly
  inferred filters.
- Add clear tests for approval, denial, missing pending deletion, and failed
  execution.
- Fix the lower-level SQLite delete issue for joined deletes.
- Add a deletion audit trail so deleted records or deletion metadata can be
  reviewed later.
- Decide whether deleted records should be restorable.

Future improvement:

- Add a soft-delete mode or backup table before destructive deletes.
- Store who approved the deletion, when it happened, what filters were used,
  and how many records were affected.

### 2. Improve Testing Coverage

The project needs layered testing because it combines normal Python functions,
database behavior, LLM routing, and user interaction.

Recommended testing layers:

- Unit tests for pure functions and validation logic.
- Database integration tests for query, insert, and delete behavior.
- Workflow tests for CLI confirmation and ADK event handling.
- Agent evaluation tests for routing and filter extraction.
- UI tests after the Streamlit interface exists.

Important test targets:

- Root agent routes deletion requests to the delete supervisor.
- Filter extraction returns valid `DeletionSchema` objects.
- Deletion preview blocks unsafe requests.
- Deletion execution only runs after confirmation.
- Cancellation clears pending deletion state.
- Insert validation catches invalid CSV rows.
- Query tools return expected results from sample data.

### 3. Refactor Interface-Specific Workflow Code

The current CLI workflow mixes agent execution, printing, and terminal input.
That is acceptable for a prototype, but it will make Streamlit or FastAPI
harder to build.

Work needed:

- Separate agent execution from CLI display logic.
- Create reusable workflow functions that return structured results.
- Keep `input()` and `print()` only in the CLI layer.
- Expose confirmation state in a way that Streamlit buttons or API endpoints
  can handle.

Suggested shape:

```text
workflow.py
  submit_request(...)
  resume_confirmation(...)

main.py
  CLI input/output only

ui/
  Streamlit app

server.py
  Optional FastAPI wrapper
```

## Product and UI Work

### 4. Design a Streamlit UI

The UI should feel like an operational database workspace, not only a chatbot.

Recommended screens:

- Assistant chat screen for natural-language requests.
- Query results table with export options.
- CSV upload and insertion review screen.
- Deletion preview screen with explicit approve/cancel buttons.
- Operation history screen.
- Logs and debugging screen for development.

Deletion UI requirement:

- The user should not need to type `APPROVE` or `CONFIRM`.
- The UI should show the preview count, table, database path, and filters.
- The final button should say something explicit like `Delete 10 records`.

### 5. Consider FastAPI as a Backend Layer

FastAPI may be useful if the UI grows beyond a local Streamlit prototype.

Potential API endpoints:

- Submit a database request.
- Resume a pending confirmation.
- Upload a CSV file.
- Export query results.
- Fetch operation history.
- Fetch logs or run status.

This can wait until the CLI and Streamlit workflows are stable.

## Data Operations Roadmap

### 6. Add Update Capabilities

After deletion is stable, the next write operation could be updating records.

Work needed:

- Create an update schema.
- Require filters for target records.
- Preview affected rows before update.
- Require confirmation before execution.
- Add audit logging for old and new values.

The update workflow should reuse the same safety pattern as deletion:

```text
infer update request
preview affected rows
ask for confirmation
execute only after approval
record audit event
```

### 7. Improve Query Result Export

Query results should be exportable so the package is useful beyond chat.

Possible export formats:

- CSV
- Excel
- JSON

Useful metadata to include:

- Original user request.
- Database path.
- Table or query target.
- Filters used.
- Export timestamp.

## Observability and Traceability

### 8. Fix and Improve Logging

Logging is currently useful for debugging, but it is not yet clean enough for
long-term usage.

Work needed:

- Make logs easier to read.
- Separate agent logs from database operation logs.
- Avoid overly noisy logs in normal CLI usage.
- Add structured logs for important operations.
- Store errors with enough context to reproduce failures.

Important events to log:

- User request received.
- Root routing decision.
- Tool calls.
- Preview results.
- Confirmation approved or denied.
- Insert, update, or delete execution result.
- Database errors.

### 9. Add Operation History and Traceability

Traceability means the user can understand what happened later.

Useful history records:

- Request text.
- Selected workflow: query, insert, update, or delete.
- Database path.
- Table.
- Filters.
- Number of records affected.
- User confirmation result.
- Timestamp.
- Error message, if failed.

For destructive operations, traceability is especially important.

## Session and State Management

### 10. Replace or Improve In-Memory Session Handling

The current session setup is good for prototyping, but future UI/API work needs
more deliberate state management.

Questions to answer:

- Should sessions be stored in SQLite?
- Should the app support multiple users?
- Should each user have separate database connections and operation history?
- How long should pending confirmations remain valid?
- Should old pending operations expire automatically?

Recommended next step:

- Keep single-user local sessions for now.
- Add a clear abstraction so SQLite-backed sessions can be introduced later.

## Agent Quality

### 11. Improve Agent Evaluation

Agent behavior should be tested with repeatable scenarios.

Important evaluation areas:

- Routing: root agent chooses the correct sub-agent.
- Filter extraction: natural language becomes correct structured filters.
- Safety: ambiguous delete requests are blocked.
- Confirmation: delete/update execution is never skipped or bypassed.
- Recovery: errors are explained clearly to the user.

Good evaluation cases:

- Simple query request.
- Simple insert request.
- Safe delete request with date filter.
- Unsafe delete request with no filters.
- Ambiguous table name.
- Invalid database path.
- User denies deletion.
- User approves deletion.

## Packaging and Documentation

### 12. Improve Developer Documentation

The project should be easy to understand and run later.

Docs to add or improve:

- Architecture overview.
- Agent workflow diagrams.
- How to run the CLI.
- How to run tests.
- How deletion confirmation works.
- Known limitations.
- Roadmap.

### 13. Clean Up Experimental Files

There are still scratch or experimental files in the repo. Before a polished
release or PR, decide whether to keep, move, or delete them.

Examples to review:

- Temporary scripts.
- Old commented code.
- Manual test files.
- Untracked local files.

## Suggested Order of Work

1. Finish deletion unit and integration tests.
2. Fix the SQLite delete implementation issue.
3. Refactor `workflow.py` so CLI logic is separated from reusable workflow
   logic.
4. Design the Streamlit UI wireframe.
5. Build a small Streamlit prototype for query and deletion confirmation.
6. Add operation history and deletion audit records.
7. Improve logging.
8. Add update-record capability.
9. Add export functionality.
10. Expand agent evaluation tests.

## Short-Term Goal

The best next milestone is:

```text
A stable local database manager that can query, insert, preview deletion,
confirm deletion, execute safely, and record what happened.
```

After that works reliably, the project can grow into a Streamlit or FastAPI
application with stronger UI, traceability, and multi-user support.
