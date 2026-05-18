"""Context usage analysis boundary for the runtime engine."""


class ContextUsageAnalyzer:
    def __init__(self, runtime):
        self.runtime = runtime

    def analyze(self, metadata):
        return self.runtime.context_usage(metadata)

