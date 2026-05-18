"""Textual widgets for the RepoHarness TUI."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from rich.text import Text
    from textual.containers import VerticalScroll
    from textual.widget import Widget
    from textual.widgets import Collapsible, Input, Markdown, Static
except Exception:  # pragma: no cover - optional dependency fallback.
    Text = None
    VerticalScroll = object
    Widget = object
    Collapsible = None
    Input = object
    Markdown = object
    Static = object


def format_tool_args(args_or_name, maybe_args=None) -> str:
    if maybe_args is None:
        name = ""
        args = args_or_name or {}
    else:
        name = str(args_or_name)
        args = maybe_args or {}
    if name == "run_shell":
        return str(args.get("command", ""))
    if name in {"read_file", "write_file", "patch_file", "list_files"}:
        path = str(args.get("path", "."))
        if name == "write_file":
            return f"{path} ({len(str(args.get('content', '')))} chars)"
        return path
    if name == "search":
        return f"{args.get('pattern', '')} in {args.get('path', '.')}"
    if name == "agent":
        return str(args.get("task", args.get("description", "")))
    return json.dumps(args, ensure_ascii=False, sort_keys=True)


class WelcomeBanner(Static):
    DEFAULT_CSS = """
    WelcomeBanner {
        height: auto;
        margin: 1 1 0 1;
        padding: 1 2;
        background: #15161c;
        color: #f1f3f8;
        border: round #5c7cfa;
    }
    """

    def __init__(self, model_name: str = "", cwd: str = "", approval: str = "") -> None:
        super().__init__()
        self.model_name = model_name
        self.cwd = cwd
        self.approval = approval

    def render(self):
        if Text is None:
            return f"RepoHarness\nmodel {self.model_name or '-'} approval {self.approval or '-'} cwd {Path(self.cwd).name if self.cwd else '-'}"
        muted = "#8b93a7"
        accent = "#9ec5fe"
        cwd_name = Path(self.cwd).name + "/" if self.cwd else "-"
        return Text.assemble(
            Text("RepoHarness", style=f"bold {accent}"),
            Text("  local repository agent\n\n", style=muted),
            Text("model ", style=muted),
            Text(self.model_name or "-", style=accent),
            Text("   approval ", style=muted),
            Text(self.approval or "-", style=accent),
            Text("   cwd ", style=muted),
            Text(cwd_name, style=accent),
            Text("\ntype /help for commands, Ctrl+L to clear, Ctrl+Q to quit", style=muted),
        )


class UserMessage(Static):
    DEFAULT_CSS = """
    UserMessage {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        color: #b7f5c1;
        border-left: thick #2f9e44;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__(markup=False)
        self.content = content

    def render(self):
        return Text.assemble(Text("> ", style="bold green"), Text(self.content, style="green")) if Text else f"> {self.content}"


class AssistantMessage(Static):
    DEFAULT_CSS = """
    AssistantMessage {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        background: #15161c;
        border-left: thick #495057;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__(markup=False)
        self.content = content

    def compose(self):
        if Markdown is not object:
            yield Markdown(self.content)

    def update_content(self, content: str) -> None:
        self.content = content
        try:
            self.query_one(Markdown).update(content)
        except Exception:
            try:
                self.update(content)
            except Exception:
                pass


class ToolCard(Static):
    DEFAULT_CSS = """
    ToolCard {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        background: #14171d;
        border: round #4dabf7;
    }
    """

    def __init__(self, tool_name: str, args_summary: str = "") -> None:
        super().__init__()
        self.tool_name = tool_name
        self.args_summary = args_summary[:120]
        self.status = "running"
        self.output = ""
        self._collapsible = None
        self._output_widget = None

    def compose(self):
        if Collapsible is None:
            return
        self._output_widget = Static("", classes="tool-output")
        self._collapsible = Collapsible(self._output_widget, title=self._label(), collapsed=False)
        yield self._collapsible

    def set_result(self, output: str, status: str = "success") -> None:
        self.status = status
        self.output = str(output)
        if self._output_widget is not None:
            self._output_widget.update(self.output[:4000])
        if self._collapsible is not None:
            self._collapsible.title = self._label()

    def _label(self) -> str:
        icon = {"running": "...", "success": "OK", "error": "ERR"}.get(self.status, "..")
        suffix = f" - {self.args_summary}" if self.args_summary else ""
        return f"{icon} {self.tool_name}{suffix}"


class ChatLog(VerticalScroll):
    DEFAULT_CSS = "ChatLog { height: 1fr; padding: 1; }"

    def add_message(self, role: str, content: str):
        widget = UserMessage(content) if role == "user" else AssistantMessage(content)
        try:
            self.mount(widget)
            self.scroll_end(animate=False)
        except Exception:
            pass
        return widget

    def add_tool_card(self, tool_name: str, args_summary: str = ""):
        card = ToolCard(tool_name, args_summary)
        try:
            self.mount(card)
            self.scroll_end(animate=False)
        except Exception:
            pass
        return card

    def clear_messages(self):
        try:
            self.remove_children()
        except Exception:
            pass


class ThinkingIndicator(Static):
    def __init__(self) -> None:
        super().__init__("")
        self.frames = ["thinking", "thinking.", "thinking..", "thinking..."]
        self.index = 0

    def show(self):
        self.index = 0
        self.update(self.frames[self.index])

    def hide(self):
        self.update("")

    def advance(self):
        self.index = (self.index + 1) % len(self.frames)
        self.update(self.frames[self.index])

    def set_detail(self, detail):
        self.update(str(detail))


class StatusBar(Static):
    def update_agent(self, agent):
        workers = len(agent.worker_manager.to_dict().get("items", []))
        todos = len(agent.todo_ledger.to_dict().get("items", []))
        self.update(f"session {agent.session['id']} | mode {agent.runtime_mode} | todos {todos} | workers {workers}")

    def update_turns(self, count):
        self.update(f"turns {count}")

    def update_context_usage(self, usage):
        self.update(f"context {usage.get('total_estimated_tokens', 0)} tokens")


class InputBar(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.history = []
        self.history_index = 0
        self.suggestions = []
        self.suggestion_index = 0
        self.input = Input(placeholder="Message RepoHarness or type /help")

    def compose(self):
        yield self.input

    def focus_input(self):
        try:
            self.input.focus()
        except Exception:
            pass

    def set_busy(self, busy: bool):
        self.input.disabled = bool(busy)

    def hide_slash_suggestions(self):
        self.suggestions = []

    def complete_slash_suggestion(self):
        if not self.suggestions:
            return False
        self.input.value = self.suggestions[self.suggestion_index]
        return True

    def move_slash_selection(self, delta):
        if not self.suggestions:
            return False
        self.suggestion_index = (self.suggestion_index + delta) % len(self.suggestions)
        return True

    def history_prev(self):
        if not self.history:
            return
        self.history_index = max(0, self.history_index - 1)
        self.input.value = self.history[self.history_index]

    def history_next(self):
        if not self.history:
            return
        self.history_index = min(len(self.history), self.history_index + 1)
        self.input.value = "" if self.history_index == len(self.history) else self.history[self.history_index]


class ConfirmPrompt(Static):
    def __init__(self, tool_name: str, args: dict) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.args = args
        self.selected = False

    def select_allow(self):
        self.selected = True
        self.update("approve")

    def select_deny(self):
        self.selected = False
        self.update("deny")


class AskUserPrompt(Static):
    def __init__(self, question: str, choices: list[str]) -> None:
        super().__init__()
        self.question = question
        self.choices = list(choices or [])
        self.index = 0

    @property
    def selected_choice(self):
        return self.choices[self.index] if self.choices else ""

    def select_next(self):
        if self.choices:
            self.index = (self.index + 1) % len(self.choices)

    def select_previous(self):
        if self.choices:
            self.index = (self.index - 1) % len(self.choices)
