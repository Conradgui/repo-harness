"""TUI entrypoint."""

from .app import RepoHarnessTextualApp


def run_tui(agent):
    app = RepoHarnessTextualApp(agent)
    return app.run()

