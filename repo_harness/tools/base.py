"""Tool abstraction shared by the runtime and prompt builder."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    schema: dict
    description: str
    risky: bool
    runner: Callable[[dict], str]

    @property
    def read_only(self):
        return not self.risky

    def execute(self, args):
        result = self.runner(args)
        if isinstance(result, ToolResult):
            return result
        return ToolResult(content=str(result))

    def __getitem__(self, key):
        if key == "run":
            return self.runner
        return getattr(self, key)

    def get(self, key, default=None):
        try:
            return self[key]
        except AttributeError:
            return default

