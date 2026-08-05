"""Runtime diagnostic logging for repo-harness.

The project's audit trail lives in ``.repo-harness`` artifacts (task_state /
trace.jsonl / report.json) and is intentionally machine-readable. This module
adds a complementary, human-facing diagnostic channel via the standard
``logging`` module:

- Default level is WARNING, so a normal run stays quiet.
- ``REPO_HARNESS_LOG_LEVEL`` (e.g. "DEBUG", "INFO") raises the level at startup.
- Output goes to stderr through a dedicated handler, so it never competes with
  the rich-based terminal UI on stdout and never rewrites trace.jsonl.

Design rule: nothing here changes existing behaviour. It only makes additional
diagnostic lines available to a developer who opts in.
"""

from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "repo_harness"
_LEVEL_NAMES = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}


def _configured_level() -> int:
    raw = os.environ.get("REPO_HARNESS_LOG_LEVEL", "").strip().upper()
    return _LEVEL_NAMES.get(raw, logging.WARNING)


def configure_logging() -> None:
    """Configure the repo_harness logger once.

    Idempotent: calling it again does not stack duplicate handlers.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(_configured_level())
    logger.propagate = False


def get_logger(name: str = "") -> logging.Logger:
    """Return a repo_harness child logger, e.g. get_logger("sandbox")."""
    configure_logging()
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)
