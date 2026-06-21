# Deletion Workflow

## Purpose

Deletion is handled as a two-step operation so that records cannot be removed
immediately from a natural-language request.

The workflow first previews the affected records and stores the validated
operation. The user must then explicitly confirm or cancel it.

## Current Flow

### 1. Deletion Request

The user submits a request such as:

```text
Delete TrackingFiles from August 3, 2023.
```

The root agent routes the request to `delete_supervisor_agent`.

### 2. Filter Extraction

`filter_infer_agent` converts the request into a structured
`DeletionSchema`:

```json
{
  "db_path": "./data/sample_data.db",
  "table": "TrackingFiles",
  "filters": {
    "date": "20230803"
  },
  "limit": 10
}
```

The schema validates the table, filter types, date format, and deletion limit.

### 3. Deletion Preview

`delete_agent` calls `preview_deletion()`.

This function:

- Rejects missing or unsupported tables.
- Rejects empty filters to prevent whole-table deletion.
- Validates filters again at the database boundary.
- Performs a dry run without deleting records.
- Stores the validated request in session state as `pending_deletion`.
- Returns the number of matching records.

The user then receives a message similar to:

```text
10 records would be deleted.
Type CONFIRM to proceed or CANCEL to abort.
```

### 4. Confirmation or Cancellation

When the user types `CONFIRM` or `CANCEL`, the root agent currently routes the
message to `deletion_confirmation_agent`.

For confirmation:

```text
CONFIRM
→ deletion_confirmation_agent
→ execute_deletion()
→ read pending_deletion
→ execute the stored database operation
```

For cancellation:

```text
CANCEL
→ deletion_confirmation_agent
→ cancel_deletion()
→ clear pending_deletion
```

The confirmation message cannot change the stored table or filters.

## Why a Separate Confirmation Agent Exists

This agent is a temporary workaround for testing through ADK Web.

ADK Web sends every user message through `root_agent`. When confirmation was
routed back to `delete_supervisor_agent`, its sequential workflow restarted:

```text
filter_infer_agent → delete_agent
```

The filter agent then received only `CONFIRM` instead of the original deletion
request. It could produce empty filters and lose the original criteria.

`deletion_confirmation_agent` avoids this by bypassing filter extraction and
operating directly on the validated deletion stored in session state.

## Why This Is Not the Final Design

Confirmation is deterministic application behavior. It does not require LLM
reasoning.

Using an agent for confirmation adds:

- An unnecessary model call.
- Additional latency and API cost.
- Another routing decision that can fail.
- Extra code and maintenance.

The current implementation is retained only to make the complete deletion flow
testable through ADK Web.

## Planned Replacement

After the database workflows are stable, confirmation handling should move into
the application workflow layer.

The intended behavior is:

```text
If a pending deletion exists:
    CONFIRM → execute the stored deletion
    CANCEL  → clear the stored deletion
Otherwise:
    send the request through the normal agent workflow
```

Conceptually:

```python
async def handle_request(message, session):
    command = message.strip().lower()

    if session.has_pending_deletion:
        if command in {"confirm", "approve", "yes"}:
            return execute_pending_deletion(session)

        if command in {"cancel", "deny", "no"}:
            return cancel_pending_deletion(session)

    return await run_agent_workflow(message, session)
```

After this is implemented:

- `deletion_confirmation_agent` can be removed.
- Confirmation will not require an LLM call.
- The same preview and session-state safety model will remain.
- CLI, API, and custom frontend clients can use the same deterministic logic.

## Current Database-Layer Limitation

The agent workflow successfully reaches `execute_deletion()`. However, joined
deletions currently fail inside the external `lab_data_manager` package because
it generates SQL similar to:

```sql
DELETE FROM TrackingFiles
JOIN Experiment
  ON TrackingFiles.experiment_id = Experiment.id
WHERE Experiment.date = :date;
```

SQLite does not support `DELETE ... JOIN` syntax. The query builder must use a
SQLite-compatible subquery, for example:

```sql
DELETE FROM TrackingFiles
WHERE id IN (
    SELECT TrackingFiles.id
    FROM TrackingFiles
    JOIN Experiment
      ON TrackingFiles.experiment_id = Experiment.id
    WHERE Experiment.date = :date
    LIMIT 10
);
```

Until that external query builder is fixed, the agent catches the error,
removes no records, and preserves `pending_deletion`.

