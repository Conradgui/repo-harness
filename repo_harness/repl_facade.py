"""REPL facade providing snapshot, suggestions, and event-driven turn execution.

This module contains the core REPL abstraction used by both the rich REPL
display layer and release evidence checks. It has no dependency on Textual
or rich -- it is a pure Python facade over the agent runtime.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashSuggestion:
    name: str
    command: str


class ReplFacade:
    """Stateful REPL controller wrapping a RepoHarness agent."""

    def __init__(self, agent):
        self.agent = agent
        self.messages = []
        self.ask_user_answers = []

    def snapshot(self):
        """Render current agent state as a text summary."""
        todos = self.agent.todo_ledger.render()
        workers = self.agent.worker_manager.to_dict().get("items", [])
        worker_text = ", ".join(f"{item['id']}:{item['status']}" for item in workers) or "none"
        return "\n".join(
            [
                "RepoHarness",
                f"session: {self.agent.session['id']}",
                f"workspace: {self.agent.workspace.cwd}",
                f"pending reviews: {len(self.agent.memory_review_pending())}",
                todos,
                f"workers: {worker_text}",
                "chat:",
                *[f"{item['role']}: {item['content']}" for item in self.messages[-8:]],
            ]
        )

    def suggest_commands(self, prefix):
        """Return slash command suggestions matching the given prefix."""
        commands = [
            "help",
            "skills",
            "skill",
            "auto-issue-fix",
            "agents",
            "subagent",
            "plan",
            "plan-exit",
            "mode",
            "usage",
            "model",
            "history",
            "context",
            "compact",
            "working-memory",
            "memory",
            "memory review",
            "memory organize",
            "memory self_iteration",
            "memory_explain",
            "remember",
            "memory_pack",
            "session",
            "reset",
            "exit",
        ]
        needle = str(prefix or "").lstrip("/")
        return [SlashSuggestion(name=name, command="/" + name) for name in commands if name.startswith(needle)]

    def ask_user(self, question, choices):
        """Callback for agent ask_user tool; returns pre-set or first choice."""
        del question
        if self.ask_user_answers:
            return self.ask_user_answers.pop(0)
        return choices[0] if choices else ""

    def run_turn(self, message):
        """Execute a user message and yield runtime events.

        This method wraps agent.ask() with the ask_user callback, records
        messages, and yields a single 'final' event for backward compatibility.
        The rich REPL bypasses this and calls engine.run_turn() directly.
        """
        previous_callback = getattr(self.agent, "ask_user_callback", None)
        self.agent.ask_user_callback = self.ask_user
        try:
            answer = self.agent.ask(message)
        finally:
            self.agent.ask_user_callback = previous_callback
        self.messages.append({"role": "user", "content": str(message)})
        self.messages.append({"role": "assistant", "content": str(answer)})
        yield {"type": "final", "content": answer}

    def run(self):
        """Print snapshot to stdout (fallback for non-rich environments)."""
        print(self.snapshot())
