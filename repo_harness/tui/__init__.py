"""Minimal RepoHarness TUI facade.

The Textual dependency is optional. Tests and non-TUI installs can still use the
snapshot renderer.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashSuggestion:
    name: str
    command: str


class RepoHarnessTuiApp:
    def __init__(self, agent):
        self.agent = agent
        self.messages = []
        self.ask_user_answers = []

    def snapshot(self):
        todos = self.agent.todo_ledger.render()
        workers = self.agent.worker_manager.to_dict().get("items", [])
        worker_text = ", ".join(f"{item['id']}:{item['status']}" for item in workers) or "none"
        return "\n".join(
            [
                "RepoHarness TUI",
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
        commands = [
            "help",
            "skills",
            "skill",
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
            "memory_explain",
            "remember",
        ]
        needle = str(prefix or "").lstrip("/")
        return [SlashSuggestion(name=name, command="/" + name) for name in commands if name.startswith(needle)]

    def ask_user(self, question, choices):
        del question
        if self.ask_user_answers:
            return self.ask_user_answers.pop(0)
        return choices[0] if choices else ""

    def run_turn(self, message):
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
        print(self.snapshot())


def run_tui(agent):
    try:
        from .main import run_tui as run_textual_tui

        return run_textual_tui(agent)
    except Exception:
        app = RepoHarnessTuiApp(agent)
        app.run()
        return app
