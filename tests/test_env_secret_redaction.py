"""Secrets loaded from a project .env (merged but never exported to
os.environ) must be redacted in tool output and session files.
"""

from repo_harness.core.secret_sanitizer import SecretSanitizer
from repo_harness.runtime import _project_env_secret_values


def test_project_env_secret_values_collects_sensitive_keys(tmp_path):
    (tmp_path / ".env").write_text(
        'DEEPSEEK_API_KEY=sk-env-only-123\nMY_API_KEY="quoted-key-456"\nNORMAL_VAR=hello\n',
        encoding="utf-8",
    )
    values = _project_env_secret_values(tmp_path)
    assert "sk-env-only-123" in values
    assert "quoted-key-456" in values
    assert "hello" not in values  # non-sensitive key value not collected


def test_sanitizer_redacts_env_file_secret_values(tmp_path):
    (tmp_path / ".env").write_text(
        "MIMO_API_KEY=sk-env-only-789\n",
        encoding="utf-8",
    )
    sanitizer = SecretSanitizer(
        secret_env_names=(),
        shell_env_allowlist=(),
        root=tmp_path,
        extra_secret_values=_project_env_secret_values(tmp_path),
    )
    text = "the key is sk-env-only-789 and it should vanish"
    redacted = sanitizer.redact_text(text)
    assert "sk-env-only-789" not in redacted
    assert "<redacted>" in redacted


def test_sanitizer_without_env_file_unchanged(tmp_path):
    sanitizer = SecretSanitizer(secret_env_names=(), shell_env_allowlist=(), root=tmp_path)
    assert sanitizer.redact_text("nothing to hide") == "nothing to hide"
