"""多步 agent 运行时使用的轻量工作记忆。

session history 负责保存完整事件流；这个模块只保存更小的一层工作集：
当前任务摘要、最近接触的文件、文件短摘要，以及少量跨轮笔记。
这样下一轮 prompt 还能接上上一轮，但不会被整段历史塞满。
"""

import ast
import configparser
import hashlib
import json
from datetime import datetime
import re
from pathlib import Path

from .workspace import clip, now

WORKING_FILE_LIMIT = 8
EPISODIC_NOTE_LIMIT = 12
FILE_SUMMARY_LIMIT = 6
PYTHON_SUMMARY_ITEM_LIMIT = 3
MARKDOWN_SUFFIXES = {".md", ".markdown"}
CONFIG_SUFFIXES = {".json", ".toml", ".ini", ".cfg", ".yaml", ".yml"}
DURABLE_REVIEW_QUEUE_SCHEMA = "durable-review-queue-v1"
DURABLE_REVIEW_QUEUE_FILE = "review-queue.jsonl"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[_.\\/-]+[A-Za-z0-9]+)*")
CAMEL_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
CAMEL_WORD_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
TOKEN_SEPARATOR_PATTERN = re.compile(r"[_.\\/-]+")
ATX_HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+[ \t]*)?$")
FENCE_OPEN_PATTERN = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
FENCE_CLOSE_PATTERN = re.compile(r"^\s{0,3}(`{3,}|~{3,})[ \t]*$")
TOML_SECTION_PATTERN = re.compile(r"^\s*\[{1,2}\s*([A-Za-z0-9_.-]+)\s*\]{1,2}\s*$")
CONFIG_KEY_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*[:=]")
YAML_TOP_LEVEL_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")

DURABLE_TOPIC_DEFAULTS = {
    "project-conventions": {
        "title": "Project Conventions",
        "summary": "Stable repository conventions.",
        "tags": ["convention"],
    },
    "key-decisions": {
        "title": "Key Decisions",
        "summary": "Long-lived decisions and rationale anchors.",
        "tags": ["decision"],
    },
    "dependency-facts": {
        "title": "Dependency Facts",
        "summary": "Stable dependency and environment facts.",
        "tags": ["dependency"],
    },
    "user-preferences": {
        "title": "User Preferences",
        "summary": "Stable user preferences.",
        "tags": ["preference"],
    },
}


def default_memory_state():
    # 用一个小而结构化的状态，而不是一大段自由文本摘要。
    return {
        "working": {
            "task_summary": "",
            "recent_files": [],
        },
        "episodic_notes": [],
        "file_summaries": {},
        "task": "",
        "files": [],
        "notes": [],
        "next_note_index": 0,
    }


class DurableMemoryStore:
    def __init__(self, root):
        self.root = Path(root)
        self.index_path = self.root / "MEMORY.md"
        self.topics_dir = self.root / "topics"

    def topic_slugs(self):
        return [topic["topic"] for topic in self.load_index()]

    def load_index(self):
        if not self.index_path.exists():
            return []
        lines = self.index_path.read_text(encoding="utf-8").splitlines()
        topics = []
        current = None
        for raw in lines:
            line = raw.strip()
            match = re.match(r"- \[([^\]]+)\]\([^)]+\):\s*(.+)", line)
            if match:
                current = {
                    "topic": match.group(1).strip(),
                    "title": match.group(2).strip(),
                    "summary": "",
                    "tags": [],
                }
                topics.append(current)
                continue
            if current is None:
                continue
            summary_match = re.match(r"- summary:\s*(.+)", line)
            if summary_match:
                current["summary"] = summary_match.group(1).strip()
                continue
            tags_match = re.match(r"- tags:\s*(.+)", line)
            if tags_match:
                current["tags"] = [tag.strip() for tag in tags_match.group(1).split(",") if tag.strip()]
        return topics

    def load_topic_notes(self, topic):
        path = self.topics_dir / f"{topic}.md"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        notes = []
        capture = False
        updated_at = ""
        tags = []
        for raw in lines:
            line = raw.strip()
            if line.startswith("- tags:"):
                tags = [tag.strip() for tag in line.split(":", 1)[1].split(",") if tag.strip()]
            elif line.startswith("- updated_at:"):
                updated_at = line.split(":", 1)[1].strip()
            elif line == "## Notes":
                capture = True
            elif capture and line.startswith("- "):
                notes.append(
                    {
                        "text": line[2:].strip(),
                        "tags": tags,
                        "source": topic,
                        "created_at": updated_at or now(),
                        "kind": "durable",
                    }
                )
        return notes

    @staticmethod
    def _subject_key(text):
        text = str(text).strip()
        patterns = (
            r"^(.+?)\s+is\s+.+$",
            r"^(.+?)\s+are\s+.+$",
            r"^(.+?)\s+uses?\s+.+$",
            r"^(.+?)\s+should\s+.+$",
            r"^(.+?)是.+$",
            r"^(.+?)使用.+$",
        )
        for pattern in patterns:
            match = re.match(pattern, text, re.I)
            if match:
                subject = _canonical_subject(match.group(1))
                return subject or None
        return None

    def retrieval_candidates(self, query, limit=3):
        return [_explanation_note_from_public(item) for item in self.retrieval_explanations(query, limit=limit)]

    def retrieval_explanations(self, query, limit=3):
        query_tokens = _tokenize(query)
        ranked = []
        for topic in self.load_index():
            notes = self.load_topic_notes(topic["topic"])
            for note in notes:
                searchable_note = dict(note)
                searchable_note["_search_text"] = topic.get("title", "")
                explanation = _explain_note_match(searchable_note, query_tokens, note_index=-1)
                if explanation is None:
                    continue
                ranked.append(explanation)
        ranked.sort(key=lambda item: item["_sort_key"], reverse=True)
        return [_public_explanation(item) for item in ranked[:limit]]

    def _write_index(self, topics):
        self.root.mkdir(parents=True, exist_ok=True)
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        lines = ["# Durable Memory Index", ""]
        for topic in topics:
            lines.append(f"- [{topic['topic']}](topics/{topic['topic']}.md): {topic['title']}")
            lines.append(f"  - summary: {topic['summary']}")
            lines.append(f"  - tags: {', '.join(topic['tags'])}")
        self.index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _write_topic(self, topic, notes):
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        meta = DURABLE_TOPIC_DEFAULTS[topic]
        lines = [
            f"# {meta['title']}",
            "",
            f"- topic: {topic}",
            f"- summary: {meta['summary']}",
            f"- tags: {', '.join(meta['tags'])}",
            f"- updated_at: {now()}",
            "",
            "## Notes",
        ]
        for note in notes:
            lines.append(f"- {note}")
        (self.topics_dir / f"{topic}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def promote(self, promotions):
        if not promotions:
            return [], []
        topics = {topic["topic"]: topic for topic in self.load_index()}
        topic_notes = {slug: [note["text"] for note in self.load_topic_notes(slug)] for slug in topics}
        results = []
        superseded = []
        for topic, note_text in promotions:
            meta = DURABLE_TOPIC_DEFAULTS[topic]
            topics.setdefault(
                topic,
                {
                    "topic": topic,
                    "title": meta["title"],
                    "summary": meta["summary"],
                    "tags": list(meta["tags"]),
                },
            )
            existing = topic_notes.setdefault(topic, [])
            if note_text in existing:
                continue
            new_subject = self._subject_key(note_text)
            replaced = False
            if new_subject:
                for index, old_text in enumerate(list(existing)):
                    if self._subject_key(old_text) == new_subject:
                        superseded.append(f"{topic}: {old_text} -> {note_text}")
                        existing[index] = note_text
                        replaced = True
                        break
            if not replaced:
                existing.append(note_text)
            results.append(f"{topic}: {note_text}")
        self._write_index([topics[slug] for slug in sorted(topics)])
        for topic, notes in topic_notes.items():
            self._write_topic(topic, notes)
        return results, superseded


class DurableMemoryReviewQueue:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / DURABLE_REVIEW_QUEUE_FILE

    def load(self):
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("schema_version") != DURABLE_REVIEW_QUEUE_SCHEMA:
                continue
            records.append(record)
        return records

    def pending(self):
        return [record for record in self.load() if record.get("status") == "pending"]

    def pending_record(self, record_id):
        for record in self.pending():
            if record.get("id") == record_id:
                return record
        return None

    def enqueue(self, promotions, source=None):
        records = self.load()
        pending_keys = {
            (str(record.get("topic", "")), str(record.get("text", "")))
            for record in records
            if record.get("status") == "pending"
        }
        existing_ids = {str(record.get("id", "")) for record in records}
        queued = []
        for topic, text in promotions:
            topic = str(topic).strip()
            text = str(text).strip()
            if topic not in DURABLE_TOPIC_DEFAULTS or not text:
                continue
            if (topic, text) in pending_keys:
                continue
            created_at = now()
            record = {
                "schema_version": DURABLE_REVIEW_QUEUE_SCHEMA,
                "id": self._new_id(topic, text, created_at, existing_ids),
                "created_at": created_at,
                "topic": topic,
                "text": text,
                "source": dict(source or {}),
                "status": "pending",
            }
            records.append(record)
            queued.append(record)
            pending_keys.add((topic, text))
            existing_ids.add(record["id"])
        if queued:
            self._write(records)
        return queued

    def mark(self, record_id, status, *, topic=None, text=None):
        records = self.load()
        updated = None
        for record in records:
            if record.get("id") != record_id or record.get("status") != "pending":
                continue
            if topic is not None:
                topic = str(topic).strip()
                if topic not in DURABLE_TOPIC_DEFAULTS:
                    raise ValueError(f"unsupported durable memory topic: {topic}")
                record["topic"] = topic
            if text is not None:
                text = str(text).strip()
                if not text:
                    raise ValueError("durable memory review text cannot be empty")
                record["text"] = text
            record["status"] = status
            record["reviewed_at"] = now()
            updated = dict(record)
            break
        if updated is not None:
            self._write(records)
        return updated

    def update_pending(self, record_id, *, topic=None, text=None):
        records = self.load()
        updated = None
        for record in records:
            if record.get("id") != record_id or record.get("status") != "pending":
                continue
            if topic is not None:
                topic = str(topic).strip()
                if topic not in DURABLE_TOPIC_DEFAULTS:
                    raise ValueError(f"unsupported durable memory topic: {topic}")
                record["topic"] = topic
            if text is not None:
                text = str(text).strip()
                if not text:
                    raise ValueError("durable memory review text cannot be empty")
                record["text"] = text
            updated = dict(record)
            break
        if updated is not None:
            self._write(records)
        return updated

    def _new_id(self, topic, text, created_at, existing_ids):
        seed = f"{created_at}\0{topic}\0{text}\0{len(existing_ids)}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        candidate = f"dmq_{digest}"
        counter = 1
        while candidate in existing_ids:
            counter += 1
            digest = hashlib.sha256(f"{seed}\0{counter}".encode("utf-8")).hexdigest()[:12]
            candidate = f"dmq_{digest}"
        return candidate

    def _write(self, records):
        self.root.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
        tmp_path.write_text(payload.rstrip() + ("\n" if records else ""), encoding="utf-8")
        tmp_path.replace(self.path)


def _ensure_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def resolve_workspace_path(raw_path, workspace_root=None):
    path = Path(str(raw_path))
    if workspace_root is None:
        return path

    root = Path(workspace_root).resolve()
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def canonicalize_path(raw_path, workspace_root=None):
    resolved = resolve_workspace_path(raw_path, workspace_root)
    if resolved is None:
        return Path(str(raw_path)).as_posix()
    if workspace_root is None:
        return Path(str(raw_path)).as_posix()
    root = Path(workspace_root).resolve()
    return resolved.relative_to(root).as_posix()


def file_freshness(raw_path, workspace_root=None):
    resolved = resolve_workspace_path(raw_path, workspace_root)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        return None
    return hashlib.sha256(resolved.read_bytes()).hexdigest()


def _split_token_parts(token):
    parts = []
    for chunk in TOKEN_SEPARATOR_PATTERN.split(str(token)):
        chunk = chunk.strip()
        if not chunk:
            continue
        chunk = CAMEL_ACRONYM_BOUNDARY.sub(r"\1 \2", chunk)
        chunk = CAMEL_WORD_BOUNDARY.sub(r"\1 \2", chunk)
        parts.extend(part for part in chunk.split() if part)
    return parts


def _tokenize(text):
    tokens = set()
    for raw_token in TOKEN_PATTERN.findall(str(text)):
        parts = _split_token_parts(raw_token)
        tokens.update(part.lower() for part in parts)
        if len(parts) > 1:
            tokens.add("".join(parts).lower())
    return tokens


def _canonical_subject(text):
    tokens = set()
    for raw_token in TOKEN_PATTERN.findall(str(text)):
        tokens.update(part.lower() for part in _split_token_parts(raw_token))
    return " ".join(sorted(tokens))


def _parse_timestamp(value):
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return 0.0


def _note_match_parts(note, query_tokens):
    note_tags = set()
    for tag in note.get("tags", []):
        note_tags.update(_tokenize(tag))
    note_tokens = _tokenize(note.get("text", "")) | _tokenize(note.get("source", "")) | _tokenize(note.get("_search_text", "")) | note_tags
    tag_match = int(bool(query_tokens & note_tags))
    keyword_overlap = len(query_tokens & note_tokens)
    recency = _parse_timestamp(note.get("created_at"))
    return tag_match, keyword_overlap, recency


def _kind_score(kind):
    return 0


def _explain_note_match(note, query_tokens, note_index=0):
    tag_match, keyword_overlap, recency = _note_match_parts(note, query_tokens)
    if tag_match == 0 and keyword_overlap == 0:
        return None

    kind = str(note.get("kind", "episodic")).strip() or "episodic"
    kind_score = _kind_score(kind)
    note_index = int(note_index)
    score_breakdown = {
        "tag_match": tag_match,
        "keyword_overlap": keyword_overlap,
        "recency": recency,
        "kind": kind_score,
    }
    score = (
        score_breakdown["tag_match"] * 1_000_000
        + score_breakdown["keyword_overlap"] * 1_000
        + score_breakdown["kind"]
        + score_breakdown["recency"] / 1_000_000_000
        + note_index / 1_000_000_000_000
    )
    return {
        "text": note.get("text", ""),
        "kind": kind,
        "source": note.get("source", ""),
        "tags": list(note.get("tags", [])),
        "created_at": note.get("created_at", ""),
        "score": score,
        "score_breakdown": score_breakdown,
        "_sort_key": (tag_match, keyword_overlap, recency, note_index),
        "_note": note,
    }


def _public_explanation(explanation):
    return {
        "text": explanation["text"],
        "kind": explanation["kind"],
        "source": explanation["source"],
        "tags": explanation["tags"],
        "created_at": explanation["created_at"],
        "score": explanation["score"],
        "score_breakdown": explanation["score_breakdown"],
    }


def _explanation_note(explanation):
    return dict(explanation["_note"])


def _explanation_note_from_public(explanation):
    return {
        "text": explanation["text"],
        "tags": list(explanation["tags"]),
        "source": explanation["source"],
        "created_at": explanation["created_at"],
        "kind": explanation["kind"],
    }


def _normalize_note(note, index):
    if isinstance(note, str):
        text = clip(note.strip(), 500)
        return {
            "text": text,
            "tags": [],
            "source": "",
            "created_at": now(),
            "note_index": index,
            "kind": "episodic",
        }

    if not isinstance(note, dict):
        text = clip(str(note).strip(), 500)
        return {
            "text": text,
            "tags": [],
            "source": "",
            "created_at": now(),
            "note_index": index,
            "kind": "episodic",
        }

    text = clip(str(note.get("text", "")).strip(), 500)
    tags = [str(tag).strip() for tag in _ensure_list(note.get("tags", [])) if str(tag).strip()]
    source = str(note.get("source", "")).strip()
    created_at = str(note.get("created_at", "")).strip() or now()
    note_index = int(note.get("note_index", index))
    kind = str(note.get("kind", "episodic")).strip() or "episodic"
    return {
        "text": text,
        "tags": _dedupe_preserve_order(tags),
        "source": source,
        "created_at": created_at,
        "note_index": note_index,
        "kind": kind,
    }


def normalize_memory_state(state, workspace_root=None):
    if state is None:
        state = default_memory_state()
    elif not isinstance(state, dict):
        raise TypeError("memory state must be a mapping")

    # 规范化层的作用，是把“磁盘里可能长得不太一样的旧状态”
    # 统一整理成当前 runtime 可直接使用的紧凑结构。
    working = state.get("working")
    if not isinstance(working, dict):
        working = {}
    working.setdefault("task_summary", "")
    working.setdefault("recent_files", [])
    working["task_summary"] = clip(str(working.get("task_summary", "")).strip(), 300)
    working["recent_files"] = _dedupe_preserve_order(
        [
            canonicalize_path(path, workspace_root)
            for path in _ensure_list(working.get("recent_files", []))
            if str(path).strip()
        ]
    )[-WORKING_FILE_LIMIT:]
    state["working"] = working

    if not str(working["task_summary"]).strip() and state.get("task"):
        working["task_summary"] = clip(str(state.get("task", "")).strip(), 300)
    if not working["recent_files"] and state.get("files"):
        working["recent_files"] = _dedupe_preserve_order(
            [
                canonicalize_path(path, workspace_root)
                for path in _ensure_list(state.get("files", []))
                if str(path).strip()
            ]
        )[-WORKING_FILE_LIMIT:]

    episodic_notes = state.get("episodic_notes")
    if not isinstance(episodic_notes, list):
        episodic_notes = []

    if not episodic_notes and state.get("notes"):
        episodic_notes = [
            _normalize_note(note, index)
            for index, note in enumerate(_ensure_list(state.get("notes", [])))
            if str(note).strip()
        ]
    else:
        normalized_notes = []
        for index, note in enumerate(episodic_notes):
            if isinstance(note, str) and not str(note).strip():
                continue
            normalized_notes.append(_normalize_note(note, index))
        episodic_notes = normalized_notes
    episodic_notes = episodic_notes[-EPISODIC_NOTE_LIMIT:]
    state["episodic_notes"] = episodic_notes

    file_summaries = state.get("file_summaries")
    if not isinstance(file_summaries, dict):
        file_summaries = {}
    normalized_file_summaries = {}
    for path, summary in file_summaries.items():
        path = canonicalize_path(path, workspace_root)
        if isinstance(summary, dict):
            text = clip(str(summary.get("summary", "")).strip(), 500)
            created_at = str(summary.get("created_at", "")).strip() or now()
            freshness = summary.get("freshness")
            freshness = None if freshness in (None, "") else str(freshness).strip() or None
        else:
            text = clip(str(summary).strip(), 500)
            created_at = now()
            freshness = None
        if not path or not text:
            continue
        normalized_file_summaries[path] = {
            "summary": text,
            "created_at": created_at,
            "freshness": freshness,
        }
    state["file_summaries"] = normalized_file_summaries

    next_note_index = state.get("next_note_index")
    if not isinstance(next_note_index, int) or next_note_index < 0:
        next_note_index = 0
    max_index = max([note["note_index"] for note in episodic_notes], default=-1)
    state["next_note_index"] = max(next_note_index, max_index + 1)

    state["task"] = working["task_summary"]
    state["files"] = list(working["recent_files"])
    state["notes"] = [note["text"] for note in episodic_notes]
    durable_root = Path(workspace_root) / ".repo-harness" / "memory" if workspace_root is not None else None
    durable_store = DurableMemoryStore(durable_root) if durable_root is not None else None
    state["durable_topics"] = durable_store.topic_slugs() if durable_store is not None else []
    return state


def set_task_summary(state, summary, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    state["working"]["task_summary"] = clip(str(summary).strip(), 300)
    state["task"] = state["working"]["task_summary"]
    return state


def remember_file(state, path, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    path = canonicalize_path(path, workspace_root).strip()
    if not path:
        return state
    files = [item for item in state["working"]["recent_files"] if item != path]
    files.append(path)
    state["working"]["recent_files"] = files[-WORKING_FILE_LIMIT:]
    state["files"] = list(state["working"]["recent_files"])
    return state


def append_note(state, text, tags=(), source="", created_at=None, workspace_root=None, kind="episodic"):
    state = normalize_memory_state(state, workspace_root)
    text = clip(str(text).strip(), 500)
    if not text:
        return state

    normalized_tags = _dedupe_preserve_order(
        [str(tag).strip() for tag in _ensure_list(tags) if str(tag).strip()]
    )
    note = {
        "text": text,
        "tags": normalized_tags,
        "source": str(source).strip(),
        "created_at": str(created_at).strip() if created_at else now(),
        "note_index": int(state.get("next_note_index", 0)),
        "kind": str(kind).strip() or "episodic",
    }
    state["next_note_index"] = note["note_index"] + 1

    notes = [item for item in state["episodic_notes"] if item["text"] != note["text"]]
    notes.append(note)
    state["episodic_notes"] = notes[-EPISODIC_NOTE_LIMIT:]
    state["notes"] = [item["text"] for item in state["episodic_notes"]]
    return state
def set_file_summary(state, path, summary, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    path = canonicalize_path(path, workspace_root).strip()
    summary = clip(str(summary).strip(), 500)
    if not path or not summary:
        return state
    state["file_summaries"][path] = {
        "summary": summary,
        "created_at": now(),
        "freshness": file_freshness(path, workspace_root),
    }
    return state


def invalidate_file_summary(state, path, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    path = canonicalize_path(path, workspace_root).strip()
    if not path:
        return state
    state["file_summaries"].pop(path, None)
    return state


def invalidate_stale_file_summaries(state, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    invalidated = []
    for path, summary in list(state["file_summaries"].items()):
        current_freshness = file_freshness(path, workspace_root)
        if summary.get("freshness") == current_freshness:
            continue
        invalidated.append(path)
        state["file_summaries"].pop(path, None)
    return state, invalidated


def _fallback_read_summary(lines, limit):
    if not lines:
        return "(empty)"
    summary = " | ".join(lines[:3])
    return clip(summary, limit)


def _split_read_result(result):
    lines = [line.rstrip() for line in str(result).splitlines() if line.strip()]
    if not lines:
        return "", [], []
    header = lines[0].strip() if lines[0].strip().startswith("# ") else ""
    body_lines = lines[1:] if header else lines
    return header[2:].strip() if header else "", body_lines, [line.strip() for line in body_lines]


def _unline_numbered_body(body_lines):
    if not body_lines:
        return None
    numbered = []
    for raw_line in body_lines:
        match = re.match(r"^\s*(\d+): ?(.*)$", raw_line)
        if match is None:
            return "\n".join(body_lines)
        numbered.append((int(match.group(1)), match.group(2)))
    if not numbered or numbered[0][0] != 1:
        return None
    return "\n".join(line for _, line in numbered)


def _unline_number_python_body(body_lines):
    return _unline_numbered_body(body_lines)


def _capped_names(names):
    names = list(names)
    shown = names[:PYTHON_SUMMARY_ITEM_LIMIT]
    value = ",".join(shown)
    remaining = len(names) - len(shown)
    if remaining > 0:
        value += f" (+{remaining})"
    return value


def _path_suffix(path_hint):
    normalized = str(path_hint or "").replace("\\", "/").rsplit("/", 1)[-1]
    return Path(normalized).suffix.lower()


def _is_test_python_path(path_hint):
    normalized = str(path_hint or "").replace("\\", "/").lower()
    basename = normalized.rsplit("/", 1)[-1]
    return basename.startswith("test_") or basename.endswith("_test.py") or "/tests/" in f"/{normalized}"


def _format_summary(prefix, parts, limit):
    parts = [(label, _dedupe_preserve_order(names)) for label, names in parts if names]
    rendered_parts = [f"{label}={_capped_names(names)}" for label, names in parts if names]
    while rendered_parts:
        summary = f"{prefix}: " + "; ".join(rendered_parts)
        if len(summary) <= limit:
            return summary
        rendered_parts.pop()
    return ""


def _summarize_markdown_source(source, limit):
    headings = []
    fence_marker = None
    fence_length = 0
    for line in source.splitlines():
        if fence_marker is not None:
            fence_match = FENCE_CLOSE_PATTERN.match(line)
            if fence_match and fence_match.group(1)[0] == fence_marker and len(fence_match.group(1)) >= fence_length:
                fence_marker = None
                fence_length = 0
            continue
        fence_match = FENCE_OPEN_PATTERN.match(line)
        if fence_match:
            fence_marker = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            continue
        match = ATX_HEADING_PATTERN.match(line)
        if match:
            heading = match.group(2).strip()
            if heading:
                headings.append(heading)
    if not headings:
        return ""
    summary = _format_summary("Markdown", [("headings", headings)], limit)
    return summary or clip("Markdown: headings", limit)


def _summarize_json_source(source, limit):
    try:
        payload = json.loads(source)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    keys = [str(key) for key in payload.keys()]
    return _format_summary("Config", [("keys", keys)], limit)


def _summarize_toml_source(source, limit):
    sections = []
    keys = []
    in_section = False
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = TOML_SECTION_PATTERN.match(line)
        if section_match:
            sections.append(section_match.group(1).strip())
            in_section = True
            continue
        if not in_section:
            key_match = CONFIG_KEY_PATTERN.match(line)
            if key_match:
                keys.append(key_match.group(1).strip())
    return _format_summary("Config", [("sections", sections), ("keys", keys)], limit)


def _summarize_ini_source(source, limit):
    parser = configparser.ConfigParser()
    parser.optionxform = str
    try:
        parser.read_string(source)
    except configparser.Error:
        return ""
    sections = parser.sections()
    keys = []
    for section in sections:
        keys.extend(parser.options(section))
    return _format_summary("Config", [("sections", sections), ("keys", keys)], limit)


def _summarize_yaml_source(source, limit):
    keys = []
    for raw_line in source.splitlines():
        if not raw_line or raw_line[0].isspace():
            continue
        line = raw_line.strip()
        if not line or line.startswith(("#", "-", "---", "...")):
            continue
        match = YAML_TOP_LEVEL_KEY_PATTERN.match(line)
        if match:
            keys.append(match.group(1).strip())
    return _format_summary("Config", [("keys", keys)], limit)


def _summarize_config_source(source, suffix, limit):
    if suffix == ".json":
        return _summarize_json_source(source, limit)
    if suffix == ".toml":
        return _summarize_toml_source(source, limit)
    if suffix in {".ini", ".cfg"}:
        return _summarize_ini_source(source, limit)
    if suffix in {".yaml", ".yml"}:
        return _summarize_yaml_source(source, limit)
    return ""


def _assignment_targets(node):
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    names = []
    for target in targets:
        if isinstance(target, ast.Name) and target.id.isupper():
            names.append(target.id)
    return names


def _python_import_name(node):
    if isinstance(node, ast.Import):
        return [alias.name.split(".", 1)[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module.split(".", 1)[0]]
    return []


def _summarize_python_source(source, limit):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    imports = []
    classes = []
    funcs = []
    constants = []
    for node in tree.body:
        imports.extend(_python_import_name(node))
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node.name)
        constants.extend(_assignment_targets(node))

    parts = []
    for label, names in (
        ("imports", _dedupe_preserve_order(imports)),
        ("classes", classes),
        ("funcs", funcs),
        ("constants", constants),
    ):
        if names:
            parts.append(f"{label}={_capped_names(names)}")
    if not parts:
        return ""

    while parts:
        summary = "Python: " + "; ".join(parts)
        if len(summary) <= limit:
            return summary
        parts.pop()
    return clip("Python: structure", limit)


def _summarize_python_test_source(source, limit):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    tests = []
    classes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            classes.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                    tests.append(f"{node.name}.{item.name}")

    return _format_summary("Tests", [("tests", tests), ("classes", classes)], limit)


def summarize_read_result(result, limit=180, complete_file=False):
    # 我们不会把完整文件内容塞进记忆层，
    # 这里只保留足够提醒下一轮“刚刚读到了什么”的短摘要。
    path_hint, body_lines, fallback_lines = _split_read_result(result)
    suffix = _path_suffix(path_hint)
    if complete_file:
        source = _unline_numbered_body(body_lines)
        if source is not None and suffix == ".py":
            if _is_test_python_path(path_hint):
                summary = _summarize_python_test_source(source, limit)
                if summary:
                    return summary
            summary = _summarize_python_source(source, limit)
            if summary:
                return summary
        if source is not None and suffix in MARKDOWN_SUFFIXES:
            summary = _summarize_markdown_source(source, limit)
            if summary:
                return summary
        if source is not None and suffix in CONFIG_SUFFIXES:
            summary = _summarize_config_source(source, suffix, limit)
            if summary:
                return summary
    return _fallback_read_summary(fallback_lines, limit)


def retrieval_candidates(state, query, limit=3, workspace_root=None):
    return [
        _explanation_note(explanation)
        for explanation in _rank_retrieval_explanations(state, query, limit=limit, workspace_root=workspace_root)
    ]


def retrieval_explanations(state, query, limit=3, workspace_root=None):
    return [
        _public_explanation(explanation)
        for explanation in _rank_retrieval_explanations(state, query, limit=limit, workspace_root=workspace_root)
    ]


def _rank_retrieval_explanations(state, query, limit=3, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    query_tokens = _tokenize(query)
    ranked = []
    for note in state["episodic_notes"]:
        # 召回逻辑故意保持简单透明：先看 tag 精确命中，
        # 再看关键词重叠，最后看新旧程度。这里不引入 embedding。
        explanation = _explain_note_match(note, query_tokens, note_index=note.get("note_index", 0))
        if explanation is None:
            continue
        ranked.append(explanation)

    if workspace_root is not None:
        durable_store = DurableMemoryStore(Path(workspace_root) / ".repo-harness" / "memory")
        for explanation in durable_store.retrieval_explanations(query, limit=limit):
            explanation = dict(explanation)
            explanation["_sort_key"] = (
                explanation["score_breakdown"]["tag_match"],
                explanation["score_breakdown"]["keyword_overlap"],
                explanation["score_breakdown"]["recency"],
                -1,
            )
            explanation["_note"] = _explanation_note_from_public(explanation)
            ranked.append(explanation)

    ranked.sort(key=lambda item: item["_sort_key"], reverse=True)
    return ranked[:limit]


def retrieval_view(state, query, limit=3, workspace_root=None):
    candidates = retrieval_candidates(state, query, limit=limit, workspace_root=workspace_root)
    lines = ["Relevant memory:"]
    if not candidates:
        lines.append("- none")
        return "\n".join(lines)
    for note in candidates:
        lines.append(f"- {note['text']}")
    return "\n".join(lines)


def render_memory_text(state, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    # 这里渲染的是给模型看的紧凑“仪表盘”，不是完整回放。
    # 笔记正文默认不展开，只有在相关召回时才按需拿出来。
    lines = [
        "Memory:",
        f"- task: {state['working']['task_summary'] or '-'}",
        f"- recent_files: {', '.join(state['working']['recent_files']) or '-'}",
    ]

    summaries = []
    for path in state["working"]["recent_files"][:FILE_SUMMARY_LIMIT]:
        summary = state["file_summaries"].get(path, {})
        current_freshness = file_freshness(path, workspace_root)
        if summary.get("summary", "") and summary.get("freshness") == current_freshness:
            summaries.append(f"- {path}: {summary['summary']}")
    if summaries:
        lines.append("- file_summaries:")
        lines.extend(f"  {line}" for line in summaries)
    else:
        lines.append("- file_summaries: -")

    lines.append(f"- episodic_notes: {len(state['episodic_notes'])}")
    durable_topics = state.get("durable_topics", [])
    lines.append(f"- durable_topics: {', '.join(durable_topics) or '-'}")
    return "\n".join(lines)


def is_effectively_empty(state, workspace_root=None):
    state = normalize_memory_state(state, workspace_root)
    return (
        not str(state["working"]["task_summary"]).strip()
        and not state["working"]["recent_files"]
        and not state["episodic_notes"]
        and not state["file_summaries"]
    )


class LayeredMemory:
    def __init__(self, state=None, workspace_root=None):
        self.workspace_root = workspace_root
        self.state = normalize_memory_state(state, workspace_root)
        durable_root = Path(workspace_root) / ".repo-harness" / "memory" if workspace_root is not None else None
        self.durable_store = DurableMemoryStore(durable_root) if durable_root is not None else None
        self.durable_review_queue = DurableMemoryReviewQueue(durable_root) if durable_root is not None else None

    def to_dict(self):
        self.state = normalize_memory_state(self.state, self.workspace_root)
        return self.state

    def canonical_path(self, path):
        return canonicalize_path(path, self.workspace_root)

    def set_task_summary(self, summary):
        self.state = set_task_summary(self.state, summary, self.workspace_root)
        return self

    def remember_file(self, path):
        self.state = remember_file(self.state, path, self.workspace_root)
        return self

    def append_note(self, text, tags=(), source="", created_at=None, kind="episodic"):
        self.state = append_note(
            self.state,
            text,
            tags=tags,
            source=source,
            created_at=created_at,
            workspace_root=self.workspace_root,
            kind=kind,
        )
        return self

    def set_file_summary(self, path, summary):
        self.state = set_file_summary(self.state, path, summary, self.workspace_root)
        return self

    def invalidate_file_summary(self, path):
        self.state = invalidate_file_summary(self.state, path, self.workspace_root)
        return self

    def invalidate_stale_file_summaries(self):
        self.state, invalidated = invalidate_stale_file_summaries(self.state, self.workspace_root)
        return invalidated

    def retrieval_candidates(self, query, limit=3):
        return retrieval_candidates(self.state, query, limit=limit, workspace_root=self.workspace_root)

    def retrieval_explanations(self, query, limit=3):
        return retrieval_explanations(self.state, query, limit=limit, workspace_root=self.workspace_root)

    def retrieval_view(self, query, limit=3):
        return retrieval_view(self.state, query, limit=limit, workspace_root=self.workspace_root)

    def render_memory_text(self):
        return render_memory_text(self.state, self.workspace_root)

    def enqueue_durable_reviews(self, promotions, source=None):
        if self.durable_review_queue is None:
            return []
        return self.durable_review_queue.enqueue(promotions, source=source)

    def pending_durable_reviews(self):
        if self.durable_review_queue is None:
            return []
        return self.durable_review_queue.pending()

    def accept_durable_review(self, record_id, *, topic=None, text=None):
        if self.durable_review_queue is None:
            return None, [], []
        record = self.durable_review_queue.pending_record(record_id)
        if record is None:
            return None, [], []
        final_topic = str(topic if topic is not None else record.get("topic", "")).strip()
        final_text = str(text if text is not None else record.get("text", "")).strip()
        if final_topic not in DURABLE_TOPIC_DEFAULTS:
            raise ValueError(f"unsupported durable memory topic: {final_topic}")
        if not final_text:
            raise ValueError("durable memory review text cannot be empty")
        updated = self.durable_review_queue.mark(record_id, "accepted", topic=final_topic, text=final_text)
        if updated is None:
            return None, [], []
        promoted, superseded = self.promote_durable([(final_topic, final_text)])
        return updated, promoted, superseded

    def update_pending_durable_review(self, record_id, *, topic=None, text=None):
        if self.durable_review_queue is None:
            return None
        return self.durable_review_queue.update_pending(record_id, topic=topic, text=text)

    def reject_durable_review(self, record_id):
        if self.durable_review_queue is None:
            return None
        return self.durable_review_queue.mark(record_id, "rejected")

    def skip_durable_review(self, record_id):
        if self.durable_review_queue is None:
            return None
        return self.durable_review_queue.pending_record(record_id)

    def promote_durable(self, promotions):
        if self.durable_store is None:
            return [], []
        self.state = normalize_memory_state(self.state, self.workspace_root)
        promoted, superseded = self.durable_store.promote(promotions)
        self.state = normalize_memory_state(self.state, self.workspace_root)
        return promoted, superseded

