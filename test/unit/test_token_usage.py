"""Unit tests for observability/token_usage.py — token counts and cost estimates from ADK events."""

from types import SimpleNamespace

import pytest

from observability.token_usage import describe, empty_usage, merge, usage_from_events


def make_event(model="gemini-2.5-flash", prompt=0, candidates=0, thoughts=None):
    meta = SimpleNamespace(prompt_token_count=prompt, candidates_token_count=candidates, thoughts_token_count=thoughts)
    return SimpleNamespace(usage_metadata=meta, model_version=model)


def test_events_without_usage_are_ignored():
    events = [SimpleNamespace(usage_metadata=None, model_version=None), SimpleNamespace()]
    assert usage_from_events(events) == empty_usage()


def test_counts_are_summed_per_model():
    usage = usage_from_events([
        make_event(prompt=1000, candidates=100, thoughts=50),
        make_event(prompt=2000, candidates=200),
        make_event(model="gemini-2.5-flash-lite", prompt=500, candidates=10),
    ])

    assert usage["calls"] == 3
    assert usage["input_tokens"] == 3500
    assert usage["output_tokens"] == 310
    assert usage["thinking_tokens"] == 50
    assert usage["total_tokens"] == 3860
    assert usage["by_model"]["gemini-2.5-flash"]["calls"] == 2
    assert usage["by_model"]["gemini-2.5-flash-lite"]["input_tokens"] == 500


def test_cost_bills_thinking_as_output():
    usage = usage_from_events([make_event(prompt=1_000_000, candidates=0, thoughts=1_000_000)])
    assert usage["estimated_cost_usd"] == pytest.approx(0.30 + 2.50)


def test_lite_model_uses_its_own_price():
    usage = usage_from_events([make_event(model="gemini-2.5-flash-lite", prompt=1_000_000)])
    assert usage["estimated_cost_usd"] == pytest.approx(0.10)


def test_unknown_model_counts_tokens_but_not_cost():
    usage = usage_from_events([make_event(model="some-other-model", prompt=1000)])
    assert usage["input_tokens"] == 1000
    assert usage["estimated_cost_usd"] == 0.0


def test_merge_adds_totals_and_models():
    total = empty_usage()
    merge(total, usage_from_events([make_event(prompt=100, candidates=10)]))
    merge(total, usage_from_events([make_event(prompt=200, candidates=20)]))
    assert total["calls"] == 2
    assert total["input_tokens"] == 300
    assert total["by_model"]["gemini-2.5-flash"]["output_tokens"] == 30


def test_describe_is_one_readable_line():
    text = describe(usage_from_events([make_event(prompt=4210, candidates=180)]))
    assert text.startswith("1 model call(s), 4,210 in / 180 out / 0 thinking tokens, ~$")
