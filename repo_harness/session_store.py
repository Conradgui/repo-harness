"""Session persistence for RepoHarness."""

import json
import tempfile
from pathlib import Path


class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.redact_func = None

    def path(self, session_id):
        return self.root / f"{session_id}.json"

    def save(self, session, redact_func=None):
        """原子写入 session 文件：先写临时文件，再 os.replace。"""
        path = self.path(session["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(session, indent=2, ensure_ascii=False)
        # 优先用调用方传入的脱敏函数，其次用实例级默认
        _redact = redact_func or self.redact_func
        if _redact is not None:
            content = _redact(content)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        tmp_path.replace(path)
        return path

    def load(self, session_id):
        path = self.path(session_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # session 文件损坏或不存在时返回空 session，避免 agent 启动崩溃
            return {"id": session_id, "_load_error": str(exc), "history": [], "workers": {"next_id": 1, "items": []}}

    def latest(self):
        files = sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime)
        return files[-1].stem if files else None
