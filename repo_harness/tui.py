"""Minimal RepoHarness TUI facade.

The Textual dependency is optional. Tests and non-TUI installs can still use the
snapshot renderer.
"""


class RepoHarnessTuiApp:
    def __init__(self, agent):
        self.agent = agent

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
            ]
        )

    def run(self):
        print(self.snapshot())


def run_tui(agent):
    app = RepoHarnessTuiApp(agent)
    app.run()
    return app
