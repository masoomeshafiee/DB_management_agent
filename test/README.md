# Test Suite

The test suite is organized by testing responsibility.

## `unit/`

Fast, deterministic tests that should not call Gemini or modify a real
database.

- `test_pydantic_models.py`: schema validation and normalization.
- `test_deletion_utils.py`: preview, approval, denial, and state cleanup.
- `test_workflow_confirmation.py`: CLI approval parsing and invocation resume.
- `test_agent_configuration.py`: agent tools, schemas, and workflow wiring.

## `integration/`

Tests that exercise multiple components together using temporary databases and
mocked external services where appropriate.

- `test_deletion_flow.py`
- `test_insertion_flow.py`
- `test_query_flow.py`

## `agent_eval/`

Tests and datasets that evaluate LLM-controlled behavior. These tests may
require credentials, network access, quota, and a separate test marker.

- Routing decisions
- Structured filter extraction
- Tool selection
- Safety behavior

## `ui/`

Reserved for Streamlit component and end-to-end UI tests.

## `fixtures/`

Shared test data, temporary database templates, CSV files, and expected output
examples. Existing CSV fixtures can remain in `test/insertion/` until they are
gradually reorganized.

## Suggested Commands

```bash
pytest -m unit
pytest -m integration
pytest -m agent_eval
pytest -m ui
pytest
```
