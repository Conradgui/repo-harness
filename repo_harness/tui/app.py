"""Optional Textual application for RepoHarness."""

try:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Footer, Header, Input, Static
except Exception:  # pragma: no cover - exercised when Textual is not installed.
    App = None
    ComposeResult = object

from . import RepoHarnessTuiApp


if App is None:

    class RepoHarnessTextualApp(RepoHarnessTuiApp):
        pass

else:

    class RepoHarnessTextualApp(App):
        """Textual shell that drives the same Engine.run_turn() as the REPL."""

        CSS = """
        Screen { layout: vertical; }
        #log { height: 1fr; overflow-y: auto; }
        Input { dock: bottom; }
        """

        def __init__(self, agent, **kwargs):
            super().__init__(**kwargs)
            self.agent = agent
            self.facade = RepoHarnessTuiApp(agent)

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="log"):
                yield Static(self.facade.snapshot(), id="snapshot")
            yield Input(placeholder="输入消息或 /help", id="input")
            yield Footer()

        def on_input_submitted(self, event):
            text = event.value.strip()
            event.input.value = ""
            if not text:
                return
            if text.startswith("/"):
                from ..cli import handle_repl_command

                handled, should_exit, output = handle_repl_command(self.agent, text)
                if should_exit:
                    self.exit()
                    return
                content = output if handled else "Unknown command. Use /help."
            else:
                content = ""
                for runtime_event in self.agent.engine.run_turn(text):
                    if runtime_event["type"] in {"final", "stop"}:
                        content = runtime_event["content"]
            self.query_one("#snapshot", Static).update(
                self.facade.snapshot() + f"\n\nassistant: {content}"
            )

