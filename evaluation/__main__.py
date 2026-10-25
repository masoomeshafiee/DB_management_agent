"""Command line entry point.

    python -m evaluation                          # every suite, once
    python -m evaluation --suite routing --suite deletion --runs 3
    python -m evaluation --suite deletion --case delete-unknown-table
    python -m evaluation --export                 # write ADK .evalset.json files only

Needs GOOGLE_API_KEY (read from .env). Runs against a copy of the database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os

from .report import summary_lines, write_report
from .runner import SUITES, run_suites

EVALSET_DIR = os.path.join(os.path.dirname(__file__), "evalsets")
DEFAULT_OUT_DIR = os.path.join(os.path.dirname(__file__), "results", "latest")


def export_evalsets() -> None:
    """Write each suite as an ADK eval set, viewable and editable in `adk web`."""
    os.makedirs(EVALSET_DIR, exist_ok=True)
    for suite in SUITES.values():
        path = os.path.join(EVALSET_DIR, f"{suite.name}.evalset.json")
        with open(path, "w") as f:
            f.write(suite.eval_set().model_dump_json(indent=2, by_alias=True, exclude_none=True))
            f.write("\n")
        config_path = os.path.join(EVALSET_DIR, f"{suite.name}.test_config.json")
        with open(config_path, "w") as f:
            json.dump({"criteria": suite.metrics}, f, indent=2)
            f.write("\n")
        print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", action="append", choices=list(SUITES), help="suite to run (repeatable; default: all)")
    parser.add_argument("--case", action="append", help="only these case ids (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="times to run each case (LLMs vary run to run)")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between cases, to respect rate limits")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="where to write report.md and results.json")
    parser.add_argument("--export", action="store_true", help="only write the ADK eval set files")
    args = parser.parse_args()

    if args.export:
        export_evalsets()
        return

    # ADK and the app log a lot at INFO; the report is the output that matters.
    logging.basicConfig(level=logging.WARNING)

    suites = args.suite or list(SUITES)
    results = asyncio.run(run_suites(suites, runs=args.runs, pause=args.pause, case_ids=args.case))
    report = write_report(results, args.out, args.runs)

    print()
    print("\n".join(summary_lines(results)))
    print(f"\nReport: {report}")


if __name__ == "__main__":
    main()
