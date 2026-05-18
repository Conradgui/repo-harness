"""Textual widget helpers for RepoHarness TUI."""

from dataclasses import dataclass


@dataclass
class RuntimeCard:
    title: str
    body: str


def format_tool_args(args):
    return ", ".join(f"{key}={value!r}" for key, value in sorted((args or {}).items()))

