"""Agent evaluation built on ADK's evaluation framework.

- scenarios.py  the cases (from test/scenarios/), encoded as ADK EvalCases
- metrics.py    custom ADK metrics registered next to the built-in ones
- runner.py     the suites, run with ADK's LocalEvalService
- sandbox.py    points every tool at a copy of the database
- report.py     summary, report.md and results.json

Run with `python -m evaluation`; see __main__.py for options.
"""
