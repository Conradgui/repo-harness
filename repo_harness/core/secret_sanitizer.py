"""Secret / environment-variable redaction and shell-env sanitization.

Extracted from ``RepoHarness`` so the runtime god object no longer owns
detection and redaction of sensitive environment values. The sanitizer is
constructed with the small slice of runtime state it needs
(``secret_env_names``, ``shell_env_allowlist``, ``root``); everything else it
reads from ``os.environ`` or module-level constants.
"""

import os

from ..workspace import REDACTED_VALUE

SENSITIVE_ENV_NAME_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")


class SecretSanitizer:
    def __init__(self, secret_env_names, shell_env_allowlist, root):
        self._secret_env_names = {str(name).upper() for name in (secret_env_names or ())}
        self._shell_env_allowlist = tuple(shell_env_allowlist or ())
        self._root = root

    @staticmethod
    def looks_sensitive_env_name(name):
        upper = str(name).upper()
        return any(
            upper == marker or upper.endswith((marker, f"_{marker}"))
            for marker in SENSITIVE_ENV_NAME_MARKERS
        )

    def is_secret_env_name(self, name):
        upper = str(name).upper()
        return upper in self._secret_env_names or self.looks_sensitive_env_name(upper)

    def configured_secret_env_items(self):
        items = [
            (name, value)
            for name, value in os.environ.items()
            if str(name).upper() in self._secret_env_names and value
        ]
        items.sort(key=lambda item: item[0])
        return items

    def detected_secret_env_items(self):
        items = [
            (name, value)
            for name, value in os.environ.items()
            if self.is_secret_env_name(name) and value
        ]
        items.sort(key=lambda item: item[0])
        return items

    def secret_env_summary(self):
        names = [name for name, _ in self.configured_secret_env_items()]
        return {
            "secret_env_count": len(names),
            "secret_env_names": names,
        }

    def detected_secret_env_summary(self):
        names = [name for name, _ in self.detected_secret_env_items()]
        return {
            "secret_env_count": len(names),
            "secret_env_names": names,
        }

    def redact_text(self, text):
        text = str(text)
        for _, value in sorted(
            self.detected_secret_env_items(), key=lambda item: len(item[1]), reverse=True
        ):
            text = text.replace(value, REDACTED_VALUE)
        return text

    def redact_artifact(self, value, key=None):
        if key and self.is_secret_env_name(key):
            return REDACTED_VALUE
        if isinstance(value, dict):
            return {
                str(item_key): self.redact_artifact(item_value, key=item_key)
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [self.redact_artifact(item, key=key) for item in value]
        if isinstance(value, tuple):
            return [self.redact_artifact(item, key=key) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def shell_env(self):
        env = {
            name: os.environ[name]
            for name in self._shell_env_allowlist
            if name in os.environ
        }
        for name in ("ComSpec", "SystemRoot", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
            if name in os.environ:
                env[name] = os.environ[name]
        env["PWD"] = str(self._root)
        if "PATH" not in env and os.environ.get("PATH"):
            env["PATH"] = os.environ["PATH"]
        return env
