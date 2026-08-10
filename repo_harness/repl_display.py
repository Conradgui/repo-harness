"""Rich REPL display layer for RepoHarness.

Provides formatted terminal output using the rich library:
- Welcome panel with agent info
- User input with green prefix
- Tool call/result cards with colored borders
- Markdown-rendered AI responses
- Error panels, status tables, slash command output

All rendering is done through a single Console instance. The display
layer has no dependency on the agent runtime -- it receives pre-formatted
data and renders it.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class ReplDisplay:
    """Rich REPL display layer."""

    def __init__(self, console: Console | None = None, no_color: bool = False):
        if console is not None:
            self.console = console
        elif no_color:
            self.console = Console(no_color=True, highlight=False, width=120)
        else:
            self.console = Console()
        self._step_count = 0

    # ── Welcome ──────────────────────────────────────────────────────

    def show_welcome(self, agent):
        """Display welcome panel with agent configuration info."""
        model = getattr(getattr(agent, "model_client", None), "model", "-")
        cwd = str(getattr(getattr(agent, "workspace", None), "cwd", "-"))
        cwd_name = Path(cwd).name + "/" if cwd != "-" else "-"
        approval = getattr(agent, "approval_policy", "-")
        session_id = agent.session.get("id", "-")

        content = Text.assemble(
            ("model ", "dim"),
            (str(model), "cyan"),
            ("   approval ", "dim"),
            (str(approval), "cyan"),
            ("   cwd ", "dim"),
            (cwd_name, "cyan"),
            ("\nsession ", "dim"),
            (session_id, "cyan"),
            ("\n\ntype /help for commands. Try:\n", "dim"),
            ("  fix the failing tests", "green"),
            ("              # talk to the agent\n", "dim"),
            ("  /skills", "green"),
            ("                           # list skills\n", "dim"),
            ("  /help", "green"),
            ("                            # all commands\n", "dim"),
        )
        self.console.print(Panel(content, title="[bold cyan]RepoHarness[/]", border_style="cyan"))

    # ── User Input ───────────────────────────────────────────────────

    def show_user_input(self, text: str):
        """Display user input with green prefix."""
        self.console.print(Text.assemble(("> ", "bold green"), (text, "green")))

    # ── Thinking ─────────────────────────────────────────────────────

    def show_thinking(self, detail: str = "thinking"):
        """Display thinking spinner."""
        self._step_count += 1
        self.hide_thinking()
        self._status = self.console.status(f"[dim]{detail}...[/]")
        self._status.start()

    def hide_thinking(self):
        """Stop thinking spinner if running."""
        status = getattr(self, "_status", None)
        if status is not None:
            # A spinner that refuses to stop is cosmetic; clearing the handle
            # matters more than the failure.
            with contextlib.suppress(Exception):
                status.stop()
            self._status = None

    # ── Tool Call / Result ───────────────────────────────────────────

    def show_tool_call(self, name: str, args: dict):
        """Display tool call card with blue border."""
        summary = self._format_tool_args(name, args)
        title = f"[bold blue]{name}[/]"
        content = Text(summary, style="dim")
        self.console.print(Panel(content, title=title, border_style="blue", padding=(0, 1)))

    def show_tool_result(self, name: str, content: str, status: str = "success"):
        """Display tool result with green/red border."""
        border = "green" if status == "success" else "red"
        icon = "+" if status == "success" else "x"
        title = f"[bold {border}]{icon} {name}[/]"

        # Truncate long outputs
        display_text = content[:2000] + "..." if len(content) > 2000 else content
        self.console.print(
            Panel(
                Text(display_text, style="dim"),
                title=title,
                border_style=border,
                padding=(0, 1),
            )
        )

    # ── AI Response ──────────────────────────────────────────────────

    def show_response(self, content: str):
        """Render AI response with Markdown formatting."""
        try:
            self.console.print(Markdown(content))
        except Exception:
            # rich Markdown rendering can fail on malformed input or terminals
            # that lack the capabilities it expects; plain text is always safe.
            self.console.print(content)

    # ── Error ────────────────────────────────────────────────────────

    def show_error(self, message: str):
        """Display error in red panel."""
        self.console.print(Panel(Text(message, style="red"), title="[bold red]Error[/]", border_style="red"))

    # ── Slash Command Output ─────────────────────────────────────────

    def show_slash_output(self, title: str, content: str):
        """Display slash command output in a panel."""
        self.console.print(Panel(content, title=f"[bold]{title}[/]", border_style="dim"))

    def show_table(self, title: str, table: Table):
        """Display a rich table."""
        self.console.print(table)

    # ── Status ───────────────────────────────────────────────────────

    def show_status(self, agent):
        """Display status summary after a turn."""
        session_id = agent.session.get("id", "-")[:16]
        mode = getattr(agent, "runtime_mode", "default")
        workers = len(agent.worker_manager.to_dict().get("items", []))
        todos = len(agent.todo_ledger.to_dict().get("items", []))
        pending = len(agent.memory_review_pending())

        status = Text.assemble(
            ("session ", "dim"),
            (session_id, "cyan"),
            ("  mode ", "dim"),
            (mode, "cyan"),
            ("  steps ", "dim"),
            (str(self._step_count), "cyan"),
            ("  workers ", "dim"),
            (str(workers), "cyan"),
            ("  todos ", "dim"),
            (str(todos), "cyan"),
        )
        if pending > 0:
            status.append(Text.assemble(("  reviews ", "dim"), (str(pending), "yellow")))

        self.console.print(status)
        self._step_count = 0

    # ── Help Table ───────────────────────────────────────────────────

    @staticmethod
    def build_help_table() -> Table:
        """Build a rich table of REPL commands."""
        table = Table(title="Commands:", show_header=True, header_style="bold")
        table.add_column("Command", style="cyan", min_width=25)
        table.add_column("Description")

        commands = [
            ("/help", "Show this help"),
            ("/skills", "List available skills"),
            ("/skill <name> [args]", "Invoke a skill"),
            ("/plan <topic>", "Enter plan mode"),
            ("/plan-exit", "Exit plan mode"),
            ("/mode", "Show current mode"),
            ("/usage", "Show context/token usage"),
            ("/model [name]", "Show or switch model"),
            ("/history", "Show conversation history"),
            ("/context", "Show context sections"),
            ("/compact", "Compact history"),
            ("/working-memory", "Show working memory"),
            ("/memory", "Show working memory distilled"),
            ("/memory review", "Review pending durable memory candidates"),
            ("/memory organize", "Organize memory candidates into Review Queue"),
            ("/memory self_iteration", "Read-only self-iteration status"),
            ("/memory_pack", "Memory pack export/import menu"),
            ("/memory_explain <q>", "Explain memory retrieval"),
            ("/remember <fact>", "Queue fact for review"),
            ("/agents", "List workers"),
            ("/subagent ...", "Spawn worker"),
            ("/auto-issue-fix", "Auto Issue Fix wizard"),
            ("/session", "Show session info"),
            ("/reset", "Reset session"),
            ("/exit", "Exit REPL"),
        ]
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        return table

    # ── Usage Table ──────────────────────────────────────────────────

    @staticmethod
    def build_usage_table(agent) -> Table:
        """Build a rich table of context/token usage."""
        table = Table(title="Context Usage", show_header=True, header_style="bold")
        table.add_column("Section", style="cyan")
        table.add_column("Chars", justify="right")
        table.add_column("Tokens", justify="right")

        try:
            usage = agent.context_usage()
            for name, section in usage.get("sections", {}).items():
                table.add_row(
                    name,
                    str(section.get("chars", 0)),
                    str(section.get("tokens", 0)),
                )
            table.add_row(
                "[bold]Total[/]",
                "",
                f"[bold]{usage.get('total_estimated_tokens', 0)}[/]",
            )
            table.add_row(
                "Free",
                "",
                str(usage.get("free_tokens", 0)),
            )
        except (KeyError, AttributeError, TypeError, ValueError):
            table.add_row("(unavailable)", "", "")

        return table

    # ── History Table ────────────────────────────────────────────────

    @staticmethod
    def build_history_table(agent) -> Table:
        """Build a rich table of recent conversation history."""
        table = Table(title="History (last 10)", show_header=True, header_style="bold")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Role", style="cyan", min_width=10)
        table.add_column("Content")

        history = agent.session.get("history", [])
        for i, item in enumerate(history[-10:]):
            role = str(item.get("role", "?"))
            content = str(item.get("content", ""))[:120]
            if item.get("role") == "tool":
                role = f"tool:{item.get('name', '?')}"
            table.add_row(str(len(history) - 10 + i), role, content)

        return table

    # ── Menu & Prompts ──────────────────────────────────────────────

    def show_menu(self, title: str, options: list):
        """Display a numbered menu using rich.table.

        Args:
            title: Menu title
            options: List of (label, description) tuples
        """
        table = Table(title=title, show_header=True, header_style="bold")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Option", style="green")
        table.add_column("Description")
        for i, (opt, desc) in enumerate(options, 1):
            table.add_row(str(i), opt, desc)
        table.add_row("0", "cancel", "Exit this menu")
        self.console.print(table)

    def prompt_choice(self, prompt: str, choices: list | None = None) -> str:
        """Display a choice prompt and return normalized input (strip + lowercase).

        Args:
            prompt: Prompt text
            choices: Optional list of valid choices for display
        """
        suffix = f" [{'/'.join(choices)}]" if choices else ""
        try:
            raw = self.console.input(f"  {prompt}{suffix} ")
        except (EOFError, KeyboardInterrupt):
            return ""
        return raw.strip().lower()

    def prompt_text(self, prompt: str, default: str = "") -> str:
        """Display a text input prompt.

        Args:
            prompt: Prompt text
            default: Default value shown in brackets
        """
        suffix = f" [{default}]" if default else ""
        try:
            raw = self.console.input(f"  {prompt}{suffix} ")
        except (EOFError, KeyboardInterrupt):
            return ""
        return raw.strip()

    def show_success(self, message: str):
        """Display a green success message."""
        self.console.print(f"  [green]✓[/] {message}")

    def show_warning(self, message: str):
        """Display a yellow warning message."""
        self.console.print(f"  [yellow]![/] {message}")

    def show_info(self, message: str):
        """Display a dim info message."""
        self.console.print(f"  [dim]{message}[/]")

    # ── Internal Helpers ─────────────────────────────────────────────

    @staticmethod
    def _format_tool_args(name: str, args: dict) -> str:
        """Format tool arguments for display."""
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
        return json.dumps(args, ensure_ascii=False, sort_keys=True)[:120]
