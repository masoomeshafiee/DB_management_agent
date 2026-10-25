# Test Suite

The test suite is organized by testing responsibility.

## `unit/`

Fast, deterministic tests. They do not call Gemini or touch a real database.

- `test_pydantic_models.py`: filter schema validation and normalization.
- `test_deletion_utils.py`: preview, approval, denial and state cleanup.
- `test_insert_utils.py`: the insert tool and its report.
- `test_workflow_confirmation.py`: approval parsing, resume, and reading results from ADK events.
- `test_agent_configuration.py`: agent tools, schemas and wiring.
- `test_token_usage.py`: token counts and cost estimates.
- `test_eval_metrics.py`: the evaluation module's metrics, scenarios and sandbox.

## `integration/`

Several components together, on a temporary copy of a real SQLite database,
with the LLM faked.

- `test_deletion_flow.py`, `test_insertion_flow.py`, `test_query_flow.py`
- `test_api.py`: the FastAPI routes.

## `agent_eval/`

The suites of the evaluation module (`evaluation/`) as pass/fail tests. They
call Gemini, so they are skipped unless `RUN_AGENT_EVAL=1` and `GOOGLE_API_KEY`
are set.

## `scenarios/`

The original hand-written request scenarios and the CSV files used by the
insertion tests and the evaluation.

## Commands

```bash
pytest test/unit test/integration -v       # no API key needed
RUN_AGENT_EVAL=1 pytest test/agent_eval -v # calls Gemini
pytest -m unit                             # by marker: unit, integration, agent_eval
```
