"""History compaction manager for the runtime split."""


class CompactManager:
    def __init__(self, runtime):
        self.runtime = runtime

    def compact(self, reason="manual"):
        return self.runtime.compact_history(reason=reason)
