"""Send traces of every agent run to a local Arize Phoenix, when switched on.

A trace shows one request as a tree: the root agent, the specialist it
transferred to, each Gemini call (prompt, response, tokens) and each tool
call (arguments and result). Useful to see *why* an agent did something.

Off by default. To use it:

    uvx --python 3.12 --from arize-phoenix==20.26.0 phoenix serve   # UI at http://localhost:6006
    PHOENIX_TRACING=1 uvicorn server:app                            # or main.py / python -m evaluation

PHOENIX_COLLECTOR_ENDPOINT overrides where traces are sent
(default http://localhost:6006). Traces include prompts and database rows,
so keep Phoenix local.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_enabled = False


def setup_tracing(project_name: str) -> bool:
    """Instrument ADK and export its spans to Phoenix if PHOENIX_TRACING is set. Returns whether it did."""
    global _enabled
    if _enabled:
        return True
    if os.getenv("PHOENIX_TRACING", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    try:
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        from phoenix.otel import register
    except ImportError:
        logger.warning("PHOENIX_TRACING is set but arize-phoenix-otel / openinference-instrumentation-google-adk are not installed")
        return False

    # batch=True sends spans in the background; they are flushed when the process exits.
    tracer_provider = register(project_name=project_name, batch=True, verbose=False)
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    _enabled = True
    logger.info(f"Phoenix tracing on, project '{project_name}'")
    return True
