"""Count the Gemini tokens a request used, and estimate what it cost.

Every model response ADK yields carries `usage_metadata` (input, output and
thinking tokens) and `model_version`. Summing them per model gives the usage
of one request, which workflow.py logs and returns, and which the evaluation
adds up per run.

The cost is an estimate from the list prices below. The real bill is in
Google AI Studio (Usage / Billing); check the prices there when they change.
"""

from __future__ import annotations

from typing import Iterable, Optional

# USD per 1 million tokens: (input, output). Thinking tokens are billed as
# output. Paid-tier text prices as of 2025, from
# https://ai.google.dev/gemini-api/docs/pricing — update them if that page
# changes. Longer prefixes must come first.
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}


def _price(model: str) -> Optional[tuple[float, float]]:
    return next((price for prefix, price in PRICES_PER_MILLION.items() if model.startswith(prefix)), None)


def empty_usage() -> dict:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "total_tokens": 0,
            "estimated_cost_usd": 0.0, "by_model": {}}


def add_event(usage: dict, event) -> None:
    """Add one ADK event's token counts to `usage`. Events without usage are ignored."""
    meta = getattr(event, "usage_metadata", None)
    if not meta:
        return
    model = getattr(event, "model_version", None) or "unknown"
    entry = usage["by_model"].setdefault(
        model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    )
    counts = {
        "input_tokens": meta.prompt_token_count or 0,
        "output_tokens": meta.candidates_token_count or 0,
        "thinking_tokens": meta.thoughts_token_count or 0,
    }
    entry["calls"] += 1
    usage["calls"] += 1
    for key, value in counts.items():
        entry[key] += value
        usage[key] += value
    usage["total_tokens"] += sum(counts.values())

    price = _price(model)
    if price:
        input_price, output_price = price
        usage["estimated_cost_usd"] += (
            counts["input_tokens"] * input_price
            + (counts["output_tokens"] + counts["thinking_tokens"]) * output_price
        ) / 1_000_000


def usage_from_events(events: Iterable) -> dict:
    usage = empty_usage()
    for event in events:
        add_event(usage, event)
    return usage


def merge(total: dict, usage: dict) -> None:
    """Add one usage summary into another, e.g. every case of an eval run."""
    for key in ("calls", "input_tokens", "output_tokens", "thinking_tokens", "total_tokens", "estimated_cost_usd"):
        total[key] += usage[key]
    for model, entry in usage["by_model"].items():
        target = total["by_model"].setdefault(model, {k: 0 for k in entry})
        for key, value in entry.items():
            target[key] += value


def describe(usage: dict) -> str:
    """One line for logs, e.g. '3 calls, 4,210 in / 180 out / 0 thinking tokens, ~$0.0006'."""
    return (
        f"{usage['calls']} model call(s), {usage['input_tokens']:,} in / {usage['output_tokens']:,} out / "
        f"{usage['thinking_tokens']:,} thinking tokens, ~${usage['estimated_cost_usd']:.4f}"
    )
