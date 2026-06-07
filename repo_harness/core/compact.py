"""History compaction manager for the runtime split.

Deprecated: CompactManager is no longer used by the runtime.
The runtime uses RepoHarness.compact_history() directly.
This class is kept for backward compatibility and will be removed in a future version.
"""

from ..workspace import clip, now


class CompactManager:
    """Deprecated: use RepoHarness.compact_history() instead."""

    def __init__(self, runtime):
        self.runtime = runtime

    def compact(self, trigger="manual", keep_recent_turns=3):
        history = list(self.runtime.session.get("history", []))
        pre_tokens = self._estimate_tokens(history)
        if not history:
            summary = {
                "trigger": trigger,
                "pre_tokens": 0,
                "post_tokens": 0,
                "summary": "No history to compact.",
                "created_at": now(),
            }
            self._record(summary)
            return summary
        keep_count = max(0, int(keep_recent_turns) * 2)
        recent = history[-keep_count:] if keep_count else []
        older = history[: len(history) - len(recent)]
        summary_text = self._summarize(older)
        if summary_text:
            self.runtime.session["history"] = [
                {
                    "role": "system",
                    "kind": "compact_summary",
                    "content": "Compacted session summary:\n" + summary_text,
                    "created_at": now(),
                },
                *recent,
            ]
        post_tokens = self._estimate_tokens(self.runtime.session.get("history", []))
        summary = {
            "trigger": trigger,
            "pre_tokens": pre_tokens,
            "post_tokens": post_tokens,
            "summary": summary_text,
            "kept_recent_items": len(recent),
            "compacted_items": len(older),
            "created_at": now(),
        }
        self._record(summary)
        return summary

    def _record(self, summary):
        self.runtime.session.setdefault("compactions", []).append(summary)
        self.runtime.emit_session_event(
            "compaction_created",
            trigger=summary.get("trigger", ""),
            pre_tokens=summary.get("pre_tokens", 0),
            post_tokens=summary.get("post_tokens", 0),
        )
        self.runtime.session_path = self.runtime.session_store.save(self.runtime.session)

    @staticmethod
    def _estimate_tokens(history):
        from .context_usage import estimate_tokens
        return estimate_tokens(str(history)) if history else 0

    @staticmethod
    def _summarize(history):
        if not history:
            return ""
        lines = []
        for item in history[-24:]:
            role = str(item.get("role", ""))
            if role == "tool":
                lines.append(f"- tool {item.get('name', '')}: {clip(item.get('content', ''), 160)}")
            else:
                lines.append(f"- {role}: {clip(item.get('content', ''), 160)}")
        return "\n".join(lines)
