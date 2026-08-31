"""Session persistence for RepoHarness."""

import json
import os
import tempfile
import threading
from pathlib import Path


class SessionLoadError(RuntimeError):
    """Session 文件损坏（半截 JSON 等）时的受控加载失败。"""


class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # 串行化并发保存：worker 线程与主线程都会写 session 文件，
        # 无锁的并发 write_text 会交错出损坏的 JSON。
        self._lock = threading.Lock()

    def path(self, session_id):
        return self.root / f"{session_id}.json"

    def save(self, session):
        path = self.path(session["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._serialize(session)
        with self._lock:
            # 原子写：先写临时文件再 replace，load / resume 永远只会
            # 看到完整的旧版或完整的新版，不会是半截 JSON。
            # 与 run_store._write_json_atomic 同一标准。
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
            ) as handle:
                handle.write(payload)
                temp_name = handle.name
            os.replace(temp_name, path)
        return path

    def _serialize(self, session):
        # dumps 可能撞上并发修改（worker 线程保存时主线程 record 改
        # 同一个 dict）抛 RuntimeError；短重试覆盖这个瞬时窗口。
        last_error = None
        for _ in range(3):
            try:
                return json.dumps(session, indent=2)
            except RuntimeError as exc:
                last_error = exc
        raise last_error

    def load(self, session_id):
        path = self.path(session_id)
        text = path.read_text(encoding="utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SessionLoadError(f"session file is corrupted: {path} ({exc})") from exc

    def latest(self):
        files = sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime)
        return files[-1].stem if files else None
