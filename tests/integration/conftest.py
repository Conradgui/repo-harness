"""Integration test fixtures for RepoHarness.

These tests require real API keys in environment variables.
Tests are skipped if the required keys are not present.
"""

import os

import pytest


def has_mimo_key():
    return bool(os.environ.get("MIMO_API_KEY"))


def has_deepseek_key():
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


requires_mimo = pytest.mark.skipif(
    not has_mimo_key(),
    reason="需要 MIMO_API_KEY 环境变量",
)

requires_deepseek = pytest.mark.skipif(
    not has_deepseek_key(),
    reason="需要 DEEPSEEK_API_KEY 环境变量",
)

requires_any_key = pytest.mark.skipif(
    not has_mimo_key() and not has_deepseek_key(),
    reason="需要 MIMO_API_KEY 或 DEEPSEEK_API_KEY 环境变量",
)
