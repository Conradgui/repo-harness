from pathlib import Path

import pytest

from repo_harness.core.secret_sanitizer import SecretSanitizer
from repo_harness.workspace import REDACTED_VALUE


@pytest.fixture
def sanitizer():
    return SecretSanitizer(
        secret_env_names={"MY_API_KEY", "DB_TOKEN"},
        shell_env_allowlist=("PATH", "HOME"),
        root=Path("/repo"),
    )


def test_looks_sensitive_env_name():
    assert SecretSanitizer.looks_sensitive_env_name("API_KEY")
    assert SecretSanitizer.looks_sensitive_env_name("MY_API_KEY")
    assert SecretSanitizer.looks_sensitive_env_name("db_token")
    assert not SecretSanitizer.looks_sensitive_env_name("PATH")


def test_is_secret_env_name(sanitizer):
    assert sanitizer.is_secret_env_name("MY_API_KEY")
    assert sanitizer.is_secret_env_name("db_token")
    assert not sanitizer.is_secret_env_name("PATH")


def test_detected_secret_env_items(monkeypatch, sanitizer):
    monkeypatch.setenv("MY_API_KEY", "supersecretvalue")
    monkeypatch.setenv("PATH", "/usr/bin")
    items = dict(sanitizer.detected_secret_env_items())
    assert items["MY_API_KEY"] == "supersecretvalue"
    assert "PATH" not in items


def test_redact_text_replaces_longest_first(monkeypatch, sanitizer):
    monkeypatch.setenv("MY_API_KEY", "abcdefgh")
    monkeypatch.setenv("DB_TOKEN", "abc")
    redacted = sanitizer.redact_text("abcdefgh and abc")
    assert "abcdefgh" not in redacted
    assert redacted == f"{REDACTED_VALUE} and {REDACTED_VALUE}"


def test_redact_artifact_redacts_secret_keys(monkeypatch, sanitizer):
    monkeypatch.setenv("MY_API_KEY", "secretvalue")
    artifact = {
        "MY_API_KEY": "secretvalue",
        "nested": {"DB_TOKEN": "tok"},
        "list": ["ok"],
        "plain": "visible",
    }
    out = sanitizer.redact_artifact(artifact)
    assert out["MY_API_KEY"] == REDACTED_VALUE
    assert out["nested"]["DB_TOKEN"] == REDACTED_VALUE
    assert out["plain"] == "visible"
    assert out["list"] == ["ok"]


def test_redact_artifact_tuple_returns_list(sanitizer):
    out = sanitizer.redact_artifact(("a", "b"))
    assert isinstance(out, list)
    assert out == ["a", "b"]


def test_shell_env_contains_root_and_path(monkeypatch, sanitizer):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = sanitizer.shell_env()
    assert env["PWD"] == str(sanitizer._root)
    assert env["PATH"] == "/usr/bin"
