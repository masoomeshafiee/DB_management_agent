"""Run the agents against a throwaway copy of the database.

The tools take the database path as a default argument (DEFAULT_DB_PATH),
bound when the function was defined, so changing the constant is not enough.
This swaps that default on every tool for the path of a temporary copy, and
afterwards checks that the real database file did not change.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import agent.utils as utils
from agent.config import DEFAULT_DB_PATH
from agent.root_agent import root_agent


def _checksum(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _tool_functions(agent) -> Iterator:
    """Every Python function used as a tool anywhere in the agent tree."""
    for tool in getattr(agent, "tools", None) or []:
        func = getattr(tool, "func", tool)
        if callable(func) and hasattr(func, "__defaults__"):
            yield func
    for sub_agent in agent.sub_agents:
        yield from _tool_functions(sub_agent)


def _is_real_db(value) -> bool:
    return isinstance(value, str) and os.path.abspath(value) == os.path.abspath(DEFAULT_DB_PATH)


@contextmanager
def database_copy() -> Iterator[str]:
    """Yield the path of a copy of the sample database that every tool now uses by default."""
    real_checksum = _checksum(DEFAULT_DB_PATH)
    with tempfile.TemporaryDirectory(prefix="db_eval_") as tmp:
        copy_path = os.path.join(tmp, "sample_data.db")
        shutil.copy(DEFAULT_DB_PATH, copy_path)

        patched = []
        for func in set(_tool_functions(root_agent)):
            if func.__defaults__ and any(_is_real_db(v) for v in func.__defaults__):
                patched.append((func, func.__defaults__))
                func.__defaults__ = tuple(copy_path if _is_real_db(v) else v for v in func.__defaults__)
        original_utils_default = utils.DEFAULT_DB_PATH
        utils.DEFAULT_DB_PATH = copy_path  # preview_deletion reads it at call time

        try:
            yield copy_path
        finally:
            utils.DEFAULT_DB_PATH = original_utils_default
            for func, defaults in patched:
                func.__defaults__ = defaults

    if _checksum(DEFAULT_DB_PATH) != real_checksum:
        raise RuntimeError(
            f"{DEFAULT_DB_PATH} changed during the evaluation. A tool used a path "
            "other than the sandbox copy; restore the database from your backup."
        )
