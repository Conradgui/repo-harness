"""Small runtime engine facade used by REPL and TUI entrypoints."""


class Engine:
    def __init__(self, runtime):
        self.runtime = runtime

    def run_turn(self, user_message):
        self.runtime.emit_session_event("turn_started", user_request=str(user_message))
        answer = self.runtime.ask(user_message)
        yield {"type": "final", "content": answer}
