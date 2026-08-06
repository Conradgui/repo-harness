"""Memory review, durable promotion and self-iteration.

Extracted from RepoHarness, which had grown to 108 methods. This is the
review-queue subdomain: everything that decides what gets remembered, queues it
for the user to accept, and compacts episodic notes once a turn ends.

The coordinator owns the memory state and the outcome of the last pass. It
reaches back into the runtime through three callables rather than a reference,
so the direction of the dependency stays one-way:

    persist()          -- write memory into the session and save it
    sync()             -- write memory into the session without saving
    source_context(origin) -- the session/run/task ids stamped onto a queued record

RepoHarness keeps same-named forwarders for the methods the CLI calls.
"""

import re

from .. import memory as memorylib
from ..workspace import REDACTED_VALUE, clip, now

DURABLE_MEMORY_INTENT_PATTERN = re.compile(r"(?i)\b(capture|remember|save|store|persist|note)\b")
DURABLE_MEMORY_INTENT_ZH_PATTERN = re.compile(r"(记住|保存|记录|沉淀|长期记忆|持久记忆)")
DURABLE_MEMORY_LINE_PATTERNS = (
    ("project-conventions", re.compile(r"(?i)^Project convention:\s*(.+)$")),
    ("key-decisions", re.compile(r"(?i)^Decision:\s*(.+)$")),
    ("dependency-facts", re.compile(r"(?i)^Dependency:\s*(.+)$")),
    ("user-preferences", re.compile(r"(?i)^Preference:\s*(.+)$")),
    ("project-conventions", re.compile(r"^项目约定：\s*(.+)$")),
    ("key-decisions", re.compile(r"^决策：\s*(.+)$")),
    ("dependency-facts", re.compile(r"^依赖：\s*(.+)$")),
    ("user-preferences", re.compile(r"^偏好：\s*(.+)$")),
)
SECRET_SHAPED_TEXT_PATTERN = re.compile(r"(?i)(\b(api[_ -]?key|token|secret|password)\b|sk-[A-Za-z0-9_-]{6,})")
SELF_ITERATION_KEEP_RECENT_NOTES = 8


class MemoryCoordinator:
    def __init__(self, memory, outcome, *, persist, sync, source_context):
        self.memory = memory
        self.outcome = outcome
        self._persist = persist
        self._sync = sync
        self._source_context = source_context

    def memory_review_pending(self):
        return self.memory.pending_durable_reviews()
    def _memory_review_result(self, status, record=None, promoted=None, superseded=None):
        if record is None:
            return {
                "status": "not_found",
                "record": {},
                "promoted": [],
                "superseded": [],
            }
        return {
            "status": status,
            "record": dict(record),
            "promoted": list(promoted or []),
            "superseded": list(superseded or []),
        }
    def _reject_durable_review_text(self, text):
        reason = self.reject_durable_reason(text)
        if not reason:
            return None
        return {
            "status": "rejected",
            "reason": reason,
            "record": {},
            "promoted": [],
            "superseded": [],
        }
    def memory_review_accept(self, record_id):
        record = self.memory.skip_durable_review(record_id)
        if record is None:
            return self._memory_review_result("not_found")
        rejection = self._reject_durable_review_text(record.get("text", ""))
        if rejection is not None:
            return rejection
        record, promoted, superseded = self.memory.accept_durable_review(record_id)
        if record is None:
            # G3: accept was blocked (non-ASCII canonical without an English
            # edit). No state changed, so do not persist. Surface the reason
            # clearly instead of claiming success.
            return {
                **self._memory_review_result("rejected", record),
                "reason": "canonical text is not ASCII-retrievable; edit in an English canonical or reject",
            }
        self._persist()
        return self._memory_review_result("accepted", record, promoted, superseded)
    def memory_review_edit(self, record_id, *, topic, text):
        rejection = self._reject_durable_review_text(text)
        if rejection is not None:
            return rejection
        record, promoted, superseded = self.memory.accept_durable_review(record_id, topic=topic, text=text)
        self._persist()
        return self._memory_review_result("accepted", record, promoted, superseded)
    def memory_review_reject(self, record_id):
        record = self.memory.reject_durable_review(record_id)
        self._persist()
        return self._memory_review_result("rejected", record)
    def memory_review_skip(self, record_id):
        record = self.memory.skip_durable_review(record_id)
        return self._memory_review_result("pending", record)
    def memory_self_iteration_status(self):
        return {
            **self.outcome.self_iteration_dict(),
            "pending_review_count": len(self.memory_review_pending()),
        }
    def memory_self_iteration_text(self):
        status = self.memory_self_iteration_status()
        lines = [
            "Memory self-iteration:",
            f"- last compactions: {len(status['episodic_compactions'])}",
            f"- queued candidates: {len(status['self_iteration_review_queued'])}",
            f"- rejections: {len(status['self_iteration_rejections'])}",
            f"- pending review candidates: {status['pending_review_count']}",
        ]
        for item in status["episodic_compactions"]:
            lines.append(f"  compaction: {clip(item, 160)}")
        for item in status["self_iteration_review_queued"]:
            lines.append(f"  queued: {clip(item, 160)}")
        for item in status["self_iteration_rejections"]:
            lines.append(f"  rejected: {item}")
        lines.append("This command is read-only; it does not compact memory or write durable topics.")
        lines.append("Use /memory review to accept, edit, reject, or skip pending durable memory candidates.")
        return "\n".join(lines)
    def memory_organize_text(self):
        status = self.run_memory_self_iteration()
        lines = [
            "Memory organize:",
            f"- queued candidates: {len(status.get('self_iteration_review_queued', []))}",
            f"- compactions: {len(status.get('episodic_compactions', []))}",
            f"- rejections: {len(status.get('self_iteration_rejections', []))}",
            "Durable memory is still review-gated: candidate fact -> Review Queue -> /memory review accept/edit -> durable topics.",
            "Run /memory review to accept, edit, reject, or skip candidates.",
        ]
        for item in status.get("self_iteration_review_queued", []):
            lines.append(f"  queued: {clip(item, 160)}")
        return "\n".join(lines)
    def reject_durable_reason(self, note_text):
        text = str(note_text or "").strip()
        lowered = text.lower()
        if not text:
            return "empty"
        if REDACTED_VALUE in text or SECRET_SHAPED_TEXT_PATTERN.search(text):
            return "secret_shaped"
        checkpoint_like_prefixes = (
            "current goal",
            "current blocker",
            "next step",
            "current phase",
            "key files",
            "freshness",
            "当前目标",
            "当前卡点",
            "下一步",
            "当前阶段",
            "关键文件",
            "已完成",
            "已排除",
        )
        if any(lowered.startswith(prefix) for prefix in checkpoint_like_prefixes):
            return "transient_task_state"
        if re.search(r"(?i)\b(stdout|stderr|traceback|exit_code)\b", text) or len(text) > 220:
            return "noisy_output"
        return ""
    def extract_durable_promotions(self, user_message, final_answer):
        user_text = str(user_message or "")
        if not (DURABLE_MEMORY_INTENT_PATTERN.search(user_text) or DURABLE_MEMORY_INTENT_ZH_PATTERN.search(user_text)):
            return [], []
        promotions = []
        rejections = []
        for line in str(final_answer or "").splitlines():
            text = line.strip()
            if not text or REDACTED_VALUE in text:
                continue
            for topic, pattern in DURABLE_MEMORY_LINE_PATTERNS:
                match = pattern.match(text)
                if not match:
                    continue
                note_text = match.group(1).strip()
                if note_text:
                    reason = self.reject_durable_reason(note_text)
                    if reason:
                        rejections.append(f"{topic}:{reason}")
                        break
                    promotions.append((topic, note_text))
                break
        return promotions, rejections
    def promote_durable_memory(self, user_message, final_answer):
        promotions, rejections = self.extract_durable_promotions(user_message, final_answer)
        queued_records = self.memory.enqueue_durable_reviews(promotions, source=self._source_context("durable-promotion"))
        queued = [f"{record['topic']}: {record['text']}" for record in queued_records]
        self._persist()
        self.outcome.record_durable_pass(queued=queued, rejections=rejections)
        return [], rejections, [], queued
    def _self_iteration_candidate_promotions(self, notes):
        promotions = []
        rejections = []
        seen = set()
        for note in notes:
            text = str(note.get("text", "")).strip() if isinstance(note, dict) else str(note).strip()
            if not text:
                continue
            for topic, pattern in DURABLE_MEMORY_LINE_PATTERNS:
                match = pattern.match(text)
                if not match:
                    continue
                note_text = match.group(1).strip()
                if not note_text:
                    break
                reason = self.reject_durable_reason(note_text)
                if reason:
                    rejections.append(f"{topic}:{reason}")
                    break
                key = (topic, note_text)
                if key not in seen:
                    promotions.append(key)
                    seen.add(key)
                break
        return promotions, rejections
    def _compact_episodic_notes(self):
        state = self.memory.to_dict()
        notes = list(state.get("episodic_notes", []))
        if len(notes) < memorylib.EPISODIC_NOTE_LIMIT:
            return []
        older = notes[:-SELF_ITERATION_KEEP_RECENT_NOTES]
        recent = notes[-SELF_ITERATION_KEEP_RECENT_NOTES:]
        parts = self._safe_compaction_parts(older)
        if not parts:
            return []
        summary = clip("Compacted earlier notes: " + "; ".join(parts[:4]), 500)
        compacted_note = {
            "text": summary,
            "tags": ["summary", "compacted"],
            "source": "episodic-compaction",
            "created_at": now(),
            "note_index": int(state.get("next_note_index", 0)),
            "kind": "episodic",
        }
        state["next_note_index"] = compacted_note["note_index"] + 1
        state["episodic_notes"] = [compacted_note, *recent][-memorylib.EPISODIC_NOTE_LIMIT:]
        state["notes"] = [note["text"] for note in state["episodic_notes"]]
        self.memory.state = state
        self._sync()
        return [summary]
    def _safe_compaction_parts(self, notes):
        parts = []
        for note in notes:
            text = str(note.get("text", "")).strip() if isinstance(note, dict) else str(note).strip()
            if not text or self.reject_durable_reason(text):
                continue
            if str(note.get("source", "")) == "episodic-compaction":
                continue
            parts.append(clip(text, 80))
        return parts
    def run_memory_self_iteration(self):
        source_notes = list(self.memory.to_dict().get("episodic_notes", []))
        promotions, rejections = self._self_iteration_candidate_promotions(source_notes)
        queued_records = self.memory.enqueue_durable_reviews(promotions, source=self._source_context("memory-self-iteration"))
        queued = [f"{record['topic']}: {record['text']}" for record in queued_records]
        compactions = self._compact_episodic_notes()
        self.outcome.record_self_iteration_pass(
            compactions=compactions, queued=queued, rejections=rejections
        )
        if compactions or queued:
            self._persist()
        return {
            "episodic_compactions": compactions,
            "self_iteration_review_queued": queued,
            "self_iteration_rejections": rejections,
        }
    def remember_candidate(self, text):
        original_text = str(text or "").strip()
        if not original_text:
            return {"status": "usage", "record": {}, "reason": "empty"}
        topic = "user-preferences"
        note_text = original_text
        for candidate_topic, pattern in DURABLE_MEMORY_LINE_PATTERNS:
            match = pattern.match(original_text)
            if match:
                topic = candidate_topic
                note_text = match.group(1).strip()
                break
        reason = self.reject_durable_reason(note_text)
        if reason:
            return {"status": "rejected", "record": {}, "reason": reason}
        queued = self.memory.enqueue_durable_reviews(
            [(topic, note_text)],
            source=self._source_context("user-remember"),
        )
        self._persist()
        if not queued:
            return {"status": "duplicate", "record": {}, "reason": "duplicate"}
        return {"status": "queued", "record": dict(queued[0]), "reason": ""}
    def invalidate_stale_memory(self):
        invalidated = self.memory.invalidate_stale_file_summaries()
        self._sync()
        return invalidated
