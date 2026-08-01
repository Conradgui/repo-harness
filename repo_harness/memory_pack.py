"""Memory pack export/import core.

This module is intentionally standalone and stdlib-only.  It provides a small
API that a CLI can wrap without coupling to the runtime loop.
"""

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "memory-pack-v1"
MANIFEST_NAME = "repo-harness-memory-pack.json"
PAYLOAD_PREFIX = "payload"

MODULE_DURABLE_KNOWLEDGE = "durable_knowledge"
MODULE_WORKING_CONTEXT = "working_context"
MODULE_RESUME_STATE = "resume_state"
MODULE_RUN_ARTIFACTS = "run_artifacts"

MEMORY_PACK_MODULES = (
    MODULE_DURABLE_KNOWLEDGE,
    MODULE_WORKING_CONTEXT,
    MODULE_RESUME_STATE,
    MODULE_RUN_ARTIFACTS,
)
MODULES = MEMORY_PACK_MODULES

PRESET_SAFE_TRANSFER = "safe-transfer"
PRESET_CONTINUE_WORK = "continue-work"
PRESET_FULL_RECOVERY = "full-recovery"

MEMORY_PACK_PRESETS = {
    PRESET_SAFE_TRANSFER: (MODULE_DURABLE_KNOWLEDGE,),
    PRESET_CONTINUE_WORK: (MODULE_DURABLE_KNOWLEDGE, MODULE_WORKING_CONTEXT),
    PRESET_FULL_RECOVERY: MEMORY_PACK_MODULES,
}
PRESET_MODULES = MEMORY_PACK_PRESETS

DEFAULT_PRESET = PRESET_SAFE_TRANSFER
FULL_RECOVERY_WARNING = (
    "Full recovery packs may contain prompts, tool outputs, local paths, "
    "reports, and traces."
)

WORKING_CONTEXT_ARCHIVE_PATH = f"{PAYLOAD_PREFIX}/{MODULE_WORKING_CONTEXT}/working-context.json"
IMPORT_REPORT_PREFIX = "import"
_ZIP_DATE_FLOOR = datetime(1980, 1, 1, tzinfo=timezone.utc)


class MemoryPackError(ValueError):
    """Raised when a memory pack is invalid or cannot be applied safely."""


@dataclass(frozen=True)
class _PayloadFile:
    module: str
    archive_path: str
    source_path: str
    data: bytes

    def manifest_entry(self):
        return {
            "module": self.module,
            "path": self.archive_path,
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "size": len(self.data),
            "source_path": self.source_path,
        }


def normalize_memory_modules(modules):
    """Return a deterministic module list from a comma string or iterable."""

    if modules is None:
        return []
    raw_items = modules.split(",") if isinstance(modules, str) else list(modules)

    seen = set()
    result = []
    for raw_item in raw_items:
        module = str(raw_item).strip()
        if not module or module in seen:
            continue
        if module not in MEMORY_PACK_MODULES:
            raise MemoryPackError(f"unsupported memory pack module: {module}")
        seen.add(module)
        result.append(module)
    return result


def resolve_memory_modules(preset=DEFAULT_PRESET, modules=None):
    """Resolve explicit modules or a preset into a deterministic module list."""

    if modules is not None:
        return normalize_memory_modules(modules)

    preset = str(preset or DEFAULT_PRESET).strip()
    if preset not in MEMORY_PACK_PRESETS:
        raise MemoryPackError(f"unsupported memory pack preset: {preset}")
    return list(MEMORY_PACK_PRESETS[preset])


def resolve_modules(preset=DEFAULT_PRESET, modules=None):
    """Compatibility alias used by CLI wrappers."""

    return resolve_memory_modules(preset=preset, modules=modules)


def warnings_for_memory_modules(modules, preset=None):
    """Return user-facing warnings implied by the selected modules/preset."""

    resolved = normalize_memory_modules(modules)
    warnings = []
    if str(preset or "").strip() == PRESET_FULL_RECOVERY or (
        MODULE_RESUME_STATE in resolved and MODULE_RUN_ARTIFACTS in resolved
    ):
        warnings.append(FULL_RECOVERY_WARNING)
    return warnings


def default_export_path(repo_root, created_at=None):
    """Return the default export path under .repo-harness/exports."""

    root = _repo_root(repo_root)
    created_at = created_at or _utc_now()
    timestamp = _timestamp_for_filename(created_at)
    return root / ".repo-harness" / "exports" / f"repo-harness-memory-pack-{timestamp}.zip"


def export_memory_pack(
    repo_root=".",
    *,
    preset=DEFAULT_PRESET,
    modules=None,
    output_path=None,
    session=None,
    session_path=None,
    created_at=None,
    overwrite=False,
):
    """Export selected memory modules to a zip memory pack.

    Returns a dictionary containing the output path, manifest, warnings, and
    payload counts.
    """

    root = _repo_root(repo_root)
    created_at = created_at or _utc_now()
    resolved_modules = resolve_memory_modules(preset=preset, modules=modules)
    manifest_preset = "custom" if modules is not None else str(preset or DEFAULT_PRESET).strip()
    warnings = warnings_for_memory_modules(resolved_modules, preset=manifest_preset)

    payload_files, collection_warnings = _collect_payload_files(
        root,
        resolved_modules,
        session=session,
        session_path=session_path,
    )
    warnings.extend(collection_warnings)

    payload_files = sorted(payload_files, key=lambda item: item.archive_path)
    file_entries = [item.manifest_entry() for item in payload_files]
    counts = _counts_for_payload(file_entries)
    pack_id = _pack_id(created_at, resolved_modules, file_entries)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "pack_id": pack_id,
        "created_at": created_at,
        "repo_harness_version": _repo_harness_version(),
        "preset": manifest_preset,
        "modules": resolved_modules,
        "source": {
            "cwd_hint": root.name,
            "workspace_fingerprint": _workspace_fingerprint(root),
        },
        "counts": counts,
        "warnings": warnings,
        "files": file_entries,
    }

    path = _resolve_output_path(root, output_path, created_at)
    if path.exists() and not overwrite:
        raise MemoryPackError(f"output path already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    zip_datetime = _zip_datetime(created_at)
    manifest_data = _json_bytes(manifest)
    with zipfile.ZipFile(path, "w") as archive:
        _write_zip_entry(archive, MANIFEST_NAME, manifest_data, zip_datetime)
        _write_zip_entry(archive, f"{PAYLOAD_PREFIX}/", b"", zip_datetime, is_dir=True)
        for module in resolved_modules:
            _write_zip_entry(archive, f"{PAYLOAD_PREFIX}/{module}/", b"", zip_datetime, is_dir=True)
        for payload_file in payload_files:
            _write_zip_entry(archive, payload_file.archive_path, payload_file.data, zip_datetime)

    return {
        "ok": True,
        "path": str(path),
        "pack_id": pack_id,
        "manifest": manifest,
        "counts": counts,
        "warnings": warnings,
    }


def inspect_memory_pack(pack_path):
    """Inspect a memory pack without writing to the workspace."""

    state = _read_and_validate_pack(pack_path)
    manifest = state["manifest"]
    return {
        "ok": True,
        "path": str(Path(pack_path)),
        "manifest": manifest,
        "counts": dict(manifest.get("counts", {})),
        "warnings": list(manifest.get("warnings", [])),
        "modules": list(manifest.get("modules", [])),
        "payload_file_count": len(state["payload_files"]),
    }


def validate_memory_pack(pack_path):
    """Validate a memory pack and raise MemoryPackError if it is unsafe."""

    state = _read_and_validate_pack(pack_path)
    manifest = state["manifest"]
    return {
        "ok": True,
        "path": str(Path(pack_path)),
        "schema_version": manifest.get("schema_version"),
        "pack_id": manifest.get("pack_id", ""),
        "modules": list(manifest.get("modules", [])),
        "counts": dict(manifest.get("counts", {})),
        "warnings": list(manifest.get("warnings", [])),
        "payload_file_count": len(state["payload_files"]),
    }


def import_memory_pack(repo_root, pack_path, *, imported_at=None):
    """Import a memory pack using conservative merge semantics."""

    root = _repo_root(repo_root)
    state = _read_and_validate_pack(pack_path)
    manifest = state["manifest"]
    imported_at = imported_at or _utc_now()
    report = {
        "schema_version": "memory-pack-import-report-v1",
        "imported_at": imported_at,
        "pack_path": str(Path(pack_path)),
        "pack_id": str(manifest.get("pack_id", "")),
        "modules": list(manifest.get("modules", [])),
        "manifest_counts": dict(manifest.get("counts", {})),
        "warnings": list(manifest.get("warnings", [])),
        "imported": {
            "durable_topics_copied": 0,
            "durable_topics_merged": 0,
            "durable_notes_added": 0,
            "durable_duplicate_notes_skipped": 0,
            "durable_index_topics_added": 0,
            "working_context_snapshots": 0,
            "session_files": 0,
            "run_files": 0,
        },
        "skipped": {
            "existing_files": [],
            "duplicate_durable_notes": [],
            "missing_payloads": [],
        },
        "errors": [],
    }

    zip_path = Path(pack_path)
    with zipfile.ZipFile(zip_path, "r") as archive:
        if MODULE_DURABLE_KNOWLEDGE in manifest.get("modules", []):
            _import_durable_knowledge(root, archive, state, report)
        if MODULE_WORKING_CONTEXT in manifest.get("modules", []):
            _import_working_context(root, archive, state, manifest, report)
        if MODULE_RESUME_STATE in manifest.get("modules", []):
            _copy_payload_tree(
                root,
                archive,
                state,
                f"{PAYLOAD_PREFIX}/{MODULE_RESUME_STATE}/sessions/",
                root / ".repo-harness" / "sessions",
                report,
                "session_files",
            )
        if MODULE_RUN_ARTIFACTS in manifest.get("modules", []):
            _copy_payload_tree(
                root,
                archive,
                state,
                f"{PAYLOAD_PREFIX}/{MODULE_RUN_ARTIFACTS}/runs/",
                root / ".repo-harness" / "runs",
                report,
                "run_files",
            )

    report_path = _write_import_report(root, report, imported_at)
    report["report_path"] = str(report_path)
    return report


def _collect_payload_files(root, modules, *, session=None, session_path=None):
    payload_files = []
    warnings = []
    if MODULE_DURABLE_KNOWLEDGE in modules:
        durable_files = _collect_durable_knowledge(root)
        if not durable_files:
            warnings.append("No durable memory files found under .repo-harness/memory.")
        payload_files.extend(durable_files)
    if MODULE_WORKING_CONTEXT in modules:
        payload_file, warning = _collect_working_context(root, session=session, session_path=session_path)
        payload_files.append(payload_file)
        if warning:
            warnings.append(warning)
    if MODULE_RESUME_STATE in modules:
        session_files, session_warnings = _collect_tree_module(
            root,
            root / ".repo-harness" / "sessions",
            MODULE_RESUME_STATE,
            "sessions",
        )
        if not session_files:
            warnings.append("No session files found under .repo-harness/sessions.")
        warnings.extend(session_warnings)
        payload_files.extend(session_files)
    if MODULE_RUN_ARTIFACTS in modules:
        run_files, run_warnings = _collect_tree_module(
            root,
            root / ".repo-harness" / "runs",
            MODULE_RUN_ARTIFACTS,
            "runs",
        )
        if not run_files:
            warnings.append("No run artifact files found under .repo-harness/runs.")
        warnings.extend(run_warnings)
        payload_files.extend(run_files)
    return payload_files, warnings


def _collect_durable_knowledge(root):
    memory_root = root / ".repo-harness" / "memory"
    result = []
    index_path = memory_root / "MEMORY.md"
    if index_path.is_file():
        result.append(
            _PayloadFile(
                module=MODULE_DURABLE_KNOWLEDGE,
                archive_path=f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/MEMORY.md",
                source_path=_repo_relative(index_path, root),
                data=index_path.read_bytes(),
            )
        )

    topics_root = memory_root / "topics"
    if topics_root.is_dir():
        for topic_path in sorted(topics_root.glob("*.md"), key=lambda path: path.name):
            result.append(
                _PayloadFile(
                    module=MODULE_DURABLE_KNOWLEDGE,
                    archive_path=f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/topics/{topic_path.name}",
                    source_path=_repo_relative(topic_path, root),
                    data=topic_path.read_bytes(),
                )
            )
    return result


def _collect_working_context(root, *, session=None, session_path=None):
    selected_session_path = None
    if session is None:
        selected_session_path = _resolve_session_path(root, session_path)
        if selected_session_path is not None:
            session = _read_json_file(selected_session_path)

    warning = ""
    if not isinstance(session, dict):
        session = {}
        warning = "No session file found; exported working context is empty."

    memory = session.get("memory", {})
    if not isinstance(memory, dict):
        memory = {}
    payload = {
        "schema_version": "working-context-v1",
        "session_id": str(session.get("id", "")),
        "source_session_path": _repo_relative(selected_session_path, root) if selected_session_path else "",
        "memory": memory,
    }
    return (
        _PayloadFile(
            module=MODULE_WORKING_CONTEXT,
            archive_path=WORKING_CONTEXT_ARCHIVE_PATH,
            source_path=payload["source_session_path"],
            data=_json_bytes(payload),
        ),
        warning,
    )


def _collect_tree_module(root, source_root, module, archive_subdir):
    result = []
    warnings = []
    if not source_root.is_dir():
        return result, warnings
    for path in _walk_files(source_root):
        if path.is_symlink():
            warnings.append(f"Skipped symlinked state file: {_repo_relative(path, root)}")
            continue
        try:
            resolved = path.resolve()
            source_resolved = source_root.resolve()
            if os.path.commonpath([str(source_resolved), str(resolved)]) != str(source_resolved):
                warnings.append(f"Skipped state file outside source tree: {_repo_relative(path, root)}")
                continue
        except OSError:
            warnings.append(f"Skipped unreadable state file: {_repo_relative(path, root)}")
            continue
        rel = path.relative_to(source_root).as_posix()
        result.append(
            _PayloadFile(
                module=module,
                archive_path=f"{PAYLOAD_PREFIX}/{module}/{archive_subdir}/{rel}",
                source_path=_repo_relative(path, root),
                data=path.read_bytes(),
            )
        )
    return result, warnings


def _counts_for_payload(file_entries):
    counts = {
        "durable_topics": 0,
        "durable_files": 0,
        "working_context_snapshots": 0,
        "session_files": 0,
        "run_files": 0,
        "payload_files": len(file_entries),
    }
    for entry in file_entries:
        module = entry.get("module")
        path = str(entry.get("path", ""))
        if module == MODULE_DURABLE_KNOWLEDGE:
            counts["durable_files"] += 1
            if path.startswith(f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/topics/"):
                counts["durable_topics"] += 1
        elif module == MODULE_WORKING_CONTEXT:
            counts["working_context_snapshots"] += 1
        elif module == MODULE_RESUME_STATE:
            counts["session_files"] += 1
        elif module == MODULE_RUN_ARTIFACTS:
            counts["run_files"] += 1
    return counts


def _read_and_validate_pack(pack_path):
    errors = []
    path = Path(pack_path)
    if not path.exists():
        raise MemoryPackError(f"memory pack does not exist: {path}")

    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            seen_archive_names = set()
            for name in names:
                if not _is_safe_archive_name(name):
                    errors.append(f"unsafe archive path: {name}")
                if name in seen_archive_names:
                    errors.append(f"duplicate archive entry: {name}")
                seen_archive_names.add(name)

            manifest_infos = [info for info in infos if info.filename == MANIFEST_NAME]
            if not manifest_infos:
                errors.append("missing manifest")
                _raise_if_errors(errors)
            if len(manifest_infos) > 1:
                errors.append("duplicate manifest entries")

            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except Exception as exc:
                errors.append(f"manifest is not valid JSON: {exc}")
                _raise_if_errors(errors)
            if not isinstance(manifest, dict):
                errors.append("manifest must be a JSON object")
                _raise_if_errors(errors)

            if manifest.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"unsupported schema: {manifest.get('schema_version')}")

            modules = manifest.get("modules")
            if not isinstance(modules, list):
                errors.append("manifest modules must be a list")
                modules = []
            else:
                try:
                    normalize_memory_modules(modules)
                except MemoryPackError as exc:
                    errors.append(str(exc))

            file_entries = manifest.get("files", [])
            if not isinstance(file_entries, list):
                errors.append("manifest files must be a list")
                file_entries = []

            manifest_payload_paths = {}
            for index, entry in enumerate(file_entries):
                if not isinstance(entry, dict):
                    errors.append(f"manifest file entry {index} must be an object")
                    continue
                payload_path = str(entry.get("path", ""))
                module = str(entry.get("module", ""))
                if not _is_safe_archive_name(payload_path):
                    errors.append(f"unsafe manifest payload path: {payload_path}")
                if not payload_path.startswith(f"{PAYLOAD_PREFIX}/"):
                    errors.append(f"manifest file is outside payload: {payload_path}")
                if module not in MEMORY_PACK_MODULES:
                    errors.append(f"manifest file has unsupported module: {module}")
                elif module not in modules:
                    errors.append(f"manifest file module not selected: {module}")
                elif not payload_path.startswith(f"{PAYLOAD_PREFIX}/{module}/"):
                    errors.append(f"manifest file path/module mismatch: {payload_path}")
                if payload_path in manifest_payload_paths:
                    errors.append(f"duplicate payload path in manifest: {payload_path}")
                manifest_payload_paths[payload_path] = entry

            actual_payload_paths = []
            for info in infos:
                name = info.filename
                if info.is_dir():
                    continue
                if name == MANIFEST_NAME:
                    continue
                if not name.startswith(f"{PAYLOAD_PREFIX}/"):
                    errors.append(f"unexpected archive file: {name}")
                    continue
                actual_payload_paths.append(name)

            expected = set(manifest_payload_paths)
            actual = set(actual_payload_paths)
            for missing_path in sorted(expected - actual):
                errors.append(f"payload mismatch: missing {missing_path}")
            for extra_path in sorted(actual - expected):
                errors.append(f"payload mismatch: unexpected {extra_path}")

            for payload_path in sorted(expected & actual):
                entry = manifest_payload_paths[payload_path]
                data = archive.read(payload_path)
                size = entry.get("size")
                digest = entry.get("sha256")
                if not isinstance(size, int) or size != len(data):
                    errors.append(f"payload mismatch: size differs for {payload_path}")
                if not isinstance(digest, str) or digest != hashlib.sha256(data).hexdigest():
                    errors.append(f"payload mismatch: sha256 differs for {payload_path}")

            _validate_durable_payload_content(archive, expected & actual, errors)
            _validate_working_context_payload_content(archive, expected & actual, errors)

            _raise_if_errors(errors)
            return {
                "manifest": manifest,
                "payload_files": manifest_payload_paths,
            }
    except zipfile.BadZipFile as exc:
        raise MemoryPackError(f"invalid zip memory pack: {exc}") from exc


def _import_durable_knowledge(root, archive, state, report):
    memory_root = root / ".repo-harness" / "memory"
    topic_prefix = f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/topics/"
    index_path = f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/MEMORY.md"
    imported_topic_blocks = {}
    imported_index_data = None

    if index_path in state["payload_files"]:
        imported_index_data = archive.read(index_path)
        try:
            imported_topic_blocks = _parse_index_blocks(imported_index_data)
        except UnicodeDecodeError:
            report["errors"].append("durable index is not UTF-8; index merge skipped")
            imported_index_data = None
            imported_topic_blocks = {}

    topic_entries = [
        path
        for path in sorted(state["payload_files"])
        if path.startswith(topic_prefix) and path.endswith(".md")
    ]
    imported_topic_meta = {}
    for archive_path in topic_entries:
        topic_name = PurePosixPath(archive_path).name
        topic_slug = Path(topic_name).stem
        data = archive.read(archive_path)
        try:
            parsed = _parse_topic_markdown(data, topic_slug)
        except UnicodeDecodeError:
            report["errors"].append(f"durable topic is not UTF-8: {archive_path}")
            continue
        try:
            topic_slug = _validate_topic_slug(parsed["topic"] or topic_slug)
        except MemoryPackError as exc:
            report["errors"].append(str(exc))
            continue
        parsed["topic"] = topic_slug
        imported_topic_meta[topic_slug] = parsed
        destination = _safe_join(memory_root / "topics", topic_name)
        if destination.exists():
            added, duplicate_notes = _merge_topic_notes(destination, parsed["notes"])
            duplicate_notes.extend(parsed["duplicate_notes"])
            if added:
                report["imported"]["durable_topics_merged"] += 1
                report["imported"]["durable_notes_added"] += added
            if duplicate_notes:
                report["imported"]["durable_duplicate_notes_skipped"] += len(duplicate_notes)
                report["skipped"]["duplicate_durable_notes"].extend(
                    f"{topic_slug}: {note}" for note in duplicate_notes
                )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        report["imported"]["durable_topics_copied"] += 1

    _merge_durable_index(
        memory_root,
        imported_index_data,
        imported_topic_blocks,
        imported_topic_meta,
        report,
    )


def _merge_topic_notes(destination, imported_notes):
    try:
        text = destination.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0, []

    existing_notes = _notes_from_topic_text(text)
    existing_set = set(existing_notes)
    new_notes = []
    duplicate_notes = []
    seen_imported = set()
    for note in imported_notes:
        if note in seen_imported:
            duplicate_notes.append(note)
            continue
        seen_imported.add(note)
        if note in existing_set:
            duplicate_notes.append(note)
            continue
        new_notes.append(note)
        existing_set.add(note)

    if not new_notes:
        return 0, duplicate_notes

    if "## Notes" not in text:
        text = text.rstrip() + "\n\n## Notes\n"
    else:
        text = text.rstrip() + "\n"
    text += "\n".join(f"- {note}" for note in new_notes) + "\n"
    destination.write_text(text, encoding="utf-8")
    return len(new_notes), duplicate_notes


def _merge_durable_index(memory_root, imported_index_data, imported_blocks, topic_meta, report):
    index_destination = memory_root / "MEMORY.md"
    if imported_index_data is not None and not index_destination.exists():
        index_destination.parent.mkdir(parents=True, exist_ok=True)
        index_destination.write_bytes(imported_index_data)
        report["imported"]["durable_index_topics_added"] += len(imported_blocks)
        return

    if index_destination.exists():
        try:
            existing_text = index_destination.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report["errors"].append("existing durable index is not UTF-8; index merge skipped")
            return
        existing_topics = set(_parse_index_blocks(existing_text.encode("utf-8")))
        blocks_to_add = []
        for topic, lines in sorted(imported_blocks.items()):
            if topic in existing_topics:
                continue
            blocks_to_add.append(lines)
            existing_topics.add(topic)
        for topic, meta in sorted(topic_meta.items()):
            if topic in existing_topics:
                continue
            blocks_to_add.append(_index_block_from_topic_meta(topic, meta))
            existing_topics.add(topic)
        if not blocks_to_add:
            return
        updated = existing_text.rstrip() + "\n"
        if not updated.endswith("\n\n"):
            updated += "\n"
        for block in blocks_to_add:
            updated += "\n".join(block).rstrip() + "\n"
        index_destination.write_text(updated, encoding="utf-8")
        report["imported"]["durable_index_topics_added"] += len(blocks_to_add)
        return

    if topic_meta:
        index_destination.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Durable Memory Index", ""]
        for topic, meta in sorted(topic_meta.items()):
            lines.extend(_index_block_from_topic_meta(topic, meta))
        index_destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        report["imported"]["durable_index_topics_added"] += len(topic_meta)


def _import_working_context(root, archive, state, manifest, report):
    if WORKING_CONTEXT_ARCHIVE_PATH not in state["payload_files"]:
        report["skipped"]["missing_payloads"].append(WORKING_CONTEXT_ARCHIVE_PATH)
        return
    pack_id = str(manifest.get("pack_id", "")).strip() or "unknown-pack"
    filename = _safe_filename(pack_id) + ".json"
    destination = _safe_join(root / ".repo-harness" / "memory" / "imported-working-contexts", filename)
    if destination.exists():
        report["skipped"]["existing_files"].append(_repo_relative(destination, root))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(archive.read(WORKING_CONTEXT_ARCHIVE_PATH))
    report["imported"]["working_context_snapshots"] += 1


def _copy_payload_tree(root, archive, state, archive_prefix, destination_root, report, counter_name):
    for archive_path in sorted(state["payload_files"]):
        if not archive_path.startswith(archive_prefix):
            continue
        rel = archive_path[len(archive_prefix) :]
        if not rel:
            continue
        try:
            destination = _safe_join(destination_root, rel)
        except MemoryPackError as exc:
            report["errors"].append(str(exc))
            continue
        if destination.exists():
            report["skipped"]["existing_files"].append(_repo_relative(destination, root))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(archive_path))
        report["imported"][counter_name] += 1


def _write_import_report(root, report, imported_at):
    imports_root = root / ".repo-harness" / "memory" / "imports"
    imports_root.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp_for_filename(imported_at)
    path = imports_root / f"{IMPORT_REPORT_PREFIX}-{timestamp}.json"
    suffix = 1
    while path.exists():
        path = imports_root / f"{IMPORT_REPORT_PREFIX}-{timestamp}-{suffix:02d}.json"
        suffix += 1
    report["report_path"] = str(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _parse_topic_markdown(data, fallback_topic):
    text = data.decode("utf-8")
    lines = text.splitlines()
    title = ""
    summary = ""
    tags = []
    topic = fallback_topic
    notes = []
    duplicate_notes = []
    in_notes = False
    seen_notes = set()
    for raw in lines:
        line = raw.strip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("- topic:"):
            topic = line.split(":", 1)[1].strip() or fallback_topic
        elif line.startswith("- summary:"):
            summary = line.split(":", 1)[1].strip()
        elif line.startswith("- tags:"):
            tags = [tag.strip() for tag in line.split(":", 1)[1].split(",") if tag.strip()]
        elif line == "## Notes":
            in_notes = True
        elif in_notes and line.startswith("- "):
            note = line[2:].strip()
            if not note:
                continue
            if note in seen_notes:
                duplicate_notes.append(note)
                continue
            seen_notes.add(note)
            notes.append(note)
    return {
        "topic": topic,
        "title": title or topic.replace("-", " ").title(),
        "summary": summary,
        "tags": tags,
        "notes": notes,
        "duplicate_notes": duplicate_notes,
    }


def _validate_durable_payload_content(archive, payload_paths, errors):
    index_path = f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/MEMORY.md"
    if index_path in payload_paths:
        try:
            for topic in _parse_index_blocks(archive.read(index_path)):
                _validate_topic_slug(topic)
        except UnicodeDecodeError:
            errors.append("durable index is not UTF-8")
        except MemoryPackError as exc:
            errors.append(str(exc))

    topic_prefix = f"{PAYLOAD_PREFIX}/{MODULE_DURABLE_KNOWLEDGE}/topics/"
    for archive_path in sorted(payload_paths):
        if not archive_path.startswith(topic_prefix) or not archive_path.endswith(".md"):
            continue
        fallback_topic = Path(PurePosixPath(archive_path).name).stem
        try:
            parsed = _parse_topic_markdown(archive.read(archive_path), fallback_topic)
            topic_slug = _validate_topic_slug(parsed["topic"] or fallback_topic)
            if topic_slug != fallback_topic:
                errors.append(
                    f"topic file name does not match topic slug: {archive_path} declares {topic_slug}"
                )
        except UnicodeDecodeError:
            errors.append(f"durable topic is not UTF-8: {archive_path}")
        except MemoryPackError as exc:
            errors.append(str(exc))


def _validate_working_context_payload_content(archive, payload_paths, errors):
    if WORKING_CONTEXT_ARCHIVE_PATH not in payload_paths:
        return
    try:
        payload = json.loads(archive.read(WORKING_CONTEXT_ARCHIVE_PATH).decode("utf-8"))
    except UnicodeDecodeError:
        errors.append("working context payload is not UTF-8")
        return
    except json.JSONDecodeError as exc:
        errors.append(f"working context payload is not valid JSON: {exc}")
        return
    if not isinstance(payload, dict):
        errors.append("working context payload must be a JSON object")
        return
    if payload.get("schema_version") != "working-context-v1":
        errors.append(f"working context has unsupported schema: {payload.get('schema_version')}")
    if not isinstance(payload.get("memory"), dict):
        errors.append("working context memory must be a JSON object")


def _validate_topic_slug(topic):
    topic = str(topic).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", topic):
        raise MemoryPackError(f"invalid durable topic slug: {topic}")
    return topic


def _notes_from_topic_text(text):
    notes = []
    in_notes = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "## Notes":
            in_notes = True
            continue
        if in_notes and line.startswith("- "):
            note = line[2:].strip()
            if note:
                notes.append(note)
    return notes


def _parse_index_blocks(data):
    text = data.decode("utf-8")
    blocks = {}
    current_topic = None
    current_lines = []
    for raw in text.splitlines():
        match = re.match(r"- \[([^\]]+)\]\([^)]+\):\s*(.*)", raw.strip())
        if match:
            if current_topic is not None:
                blocks[current_topic] = current_lines
            current_topic = match.group(1).strip()
            current_lines = [raw.rstrip()]
            continue
        if current_topic is not None and raw.startswith((" ", "\t")):
            current_lines.append(raw.rstrip())
    if current_topic is not None:
        blocks[current_topic] = current_lines
    return blocks


def _index_block_from_topic_meta(topic, meta):
    topic = _validate_topic_slug(topic)
    title = str(meta.get("title") or topic.replace("-", " ").title()).strip()
    summary = str(meta.get("summary") or "").strip()
    tags = [str(tag).strip() for tag in meta.get("tags", []) if str(tag).strip()]
    return [
        f"- [{topic}](topics/{topic}.md): {title}",
        f"  - summary: {summary}",
        f"  - tags: {', '.join(tags)}",
    ]


def _resolve_session_path(root, session_path):
    if session_path:
        path = Path(session_path)
        if not path.is_absolute():
            path = root / path
        return path if path.is_file() else None
    sessions_root = root / ".repo-harness" / "sessions"
    if not sessions_root.is_dir():
        return None
    files = [path for path in sessions_root.glob("*.json") if path.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name))[-1]


def _read_json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_harness_version():
    try:
        return version("repo-harness")
    except PackageNotFoundError:
        return "0.1.0"


def _workspace_fingerprint(root):
    digest = hashlib.sha256()
    for rel in ("README.md", "pyproject.toml", "package.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()


def _walk_files(root):
    if not root.is_dir():
        return []
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in {"__pycache__", ".git"} and not name.endswith(".egg-info")
        )
        for filename in sorted(filenames):
            result.append(Path(dirpath) / filename)
    return result


def _repo_root(repo_root):
    return Path(repo_root).resolve()


def _repo_relative(path, root):
    if path is None:
        return ""
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _resolve_output_path(root, output_path, created_at):
    if output_path is None:
        return default_export_path(root, created_at=created_at)
    path = Path(output_path)
    if not path.is_absolute():
        path = root / path
    if path.exists() and path.is_dir():
        path = path / default_export_path(root, created_at=created_at).name
    return path


def _safe_join(root, relative_path):
    root = Path(root).resolve()
    rel = PurePosixPath(str(relative_path).replace("\\", "/"))
    if rel.is_absolute() or any(part in ("", ".", "..") or ":" in part for part in rel.parts):
        raise MemoryPackError(f"unsafe relative path: {relative_path}")
    candidate = (root / Path(*rel.parts)).resolve()
    if os.path.commonpath([str(root), str(candidate)]) != str(root):
        raise MemoryPackError(f"path escapes destination: {relative_path}")
    return candidate


def _is_safe_archive_name(name):
    name = str(name)
    if not name or "\x00" in name or "\\" in name:
        return False
    if name.startswith(("/", "\\")):
        return False
    stripped = name.rstrip("/")
    if not stripped:
        return False
    raw_parts = stripped.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        return False
    if any(":" in part for part in raw_parts):
        return False
    path = PurePosixPath(stripped)
    return not path.is_absolute()


def _safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    value = value.strip(".-")
    return value or "memory-pack"


def _json_bytes(payload):
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_for_filename(value):
    dt = _parse_datetime(value)
    return dt.strftime("%Y%m%d-%H%M%S")


def _parse_datetime(value):
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _zip_datetime(value):
    dt = _parse_datetime(value)
    if dt < _ZIP_DATE_FLOOR:
        dt = _ZIP_DATE_FLOOR
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _pack_id(created_at, modules, file_entries):
    payload = {
        "created_at": created_at,
        "modules": list(modules),
        "files": [
            {
                "module": entry.get("module"),
                "path": entry.get("path"),
                "sha256": entry.get("sha256"),
                "size": entry.get("size"),
            }
            for entry in file_entries
        ],
    }
    digest = hashlib.sha256(_json_bytes(payload)).hexdigest()[:12]
    return f"memory-pack-{_timestamp_for_filename(created_at)}-{digest}"


def _write_zip_entry(archive, name, data, date_time, is_dir=False):
    info = zipfile.ZipInfo(name, date_time=date_time)
    info.compress_type = zipfile.ZIP_DEFLATED
    if is_dir:
        info.external_attr = 0o40755 << 16
    archive.writestr(info, data)


def _raise_if_errors(errors):
    if errors:
        raise MemoryPackError("; ".join(errors))
