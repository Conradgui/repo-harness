"""Backward-compatible re-exports from repl_facade.

The canonical implementation lives in repo_harness.repl_facade.
This module re-exports for backward compatibility with release_evidence.py
and existing tests.
"""

from ..repl_facade import ReplFacade, SlashSuggestion

# Backward-compatible alias
RepoHarnessTuiApp = ReplFacade

__all__ = ["ReplFacade", "RepoHarnessTuiApp", "SlashSuggestion"]
