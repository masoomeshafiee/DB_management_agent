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
Review the approval request to proceed or reject the deletion.
```

### 4. Native Tool Confirmation

After a successful preview, `delete_agent` requests the `execute_deletion`
tool. That tool is registered with native ADK confirmation enabled.

```text
preview_deletion()
→ store pending_deletion
→ request execute_deletion()
→ ADK pauses the tool call
```

The interface collects the user's decision:

- ADK Web displays its approval controls.
- The CLI detects the confirmation event and asks through `input()`.
- A future Streamlit interface can display approve and reject buttons.

After the response:

```text
Approved
→ execute_deletion reads pending_deletion
→ clear pending_deletion
→ execute the stored database operation

Rejected
→ execute_deletion clears pending_deletion
→ return without deleting records
```

The approval response cannot provide or modify deletion filters. Execution uses
only the validated request saved during preview.

## Interface Responsibilities

The database tools do not directly collect user input.

ADK provides a confirmation event when the protected execution tool is
requested. Each interface presents that event differently:

```text
ADK Web   → graphical approval controls
CLI       → terminal approval prompt in workflow.py
Streamlit → application approval buttons
```

All interfaces resume the same protected tool call, so the underlying deletion
implementation remains shared.

## State Cleanup

`pending_deletion` is cleared when:

- The preview finds no matching records.
- The preview fails.
- The user rejects confirmation.
- The user approves confirmation, before database execution begins.

If database execution fails, the user must run a new preview before retrying.
This prevents an old pending request from remaining active.

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
removes no records, and clears `pending_deletion`.
