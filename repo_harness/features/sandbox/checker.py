"""Sandbox backend checker."""

from shutil import which as default_which


class SandboxChecker:
    def __init__(self, which=None):
        self.which = which or default_which

    def backend_path(self, backend):
        backend = str(backend or "auto")
        if backend in {"native", "off", "none"}:
            return ""
        if backend == "auto":
            return self.which("bwrap") or self.which("bubblewrap") or ""
        if backend == "bubblewrap":
            return self.which("bwrap") or self.which("bubblewrap") or ""
        return ""

