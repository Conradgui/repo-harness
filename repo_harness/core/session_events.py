"""Session-level event bus."""

import json
from pathlib import Path

from ..workspace import now


class SessionEventBus:
    def __init__(self, session_id, path, redact=None):
        self.session_id = str(session_id)
        self.path = Path(path)
        self.redact = redact or (lambda value: value)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event, payload=None, **kwargs):
        record = dict(payload or {})
        record.update(kwargs)
        record["event"] = str(event)
        record["session_id"] = self.session_id
        record["created_at"] = now()
        record = self.redact(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
        return record
