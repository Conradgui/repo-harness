"""Session-scoped runtime event log."""

import json
from pathlib import Path

from .workspace import now


class SessionEventBus:
    def __init__(self, root, session_id):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id = str(session_id)
        self.path = self.root / f"{self.session_id}.events.jsonl"

    def emit(self, event, **payload):
        record = {
            "event": str(event),
            "session_id": self.session_id,
            "created_at": now(),
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
        return record
