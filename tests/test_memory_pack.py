import importlib
import json
import os
import re
import zipfile
from pathlib import Path

import pytest

MANIFEST_NAME = "repo-harness-memory-pack.json"
WORKING_CONTEXT_MEMBER = "payload/working_context/working-context.json"


def memory_pack_api():
    try:
        return importlib.import_module("repo_harness.memory_pack")
    except ModuleNotFoundError as exc:
        if exc.name == "repo_harness.memory_pack":
            pytest.fail(
                "repo_harness.memory_pack must expose export_memory_pack, "
                "import_memory_pack, inspect_memory_pack, and validate_memory_pack"
            )
        raise


def baseline_manifest(preset="safe-transfer", modules=("durable_knowledge",), counts=None, warnings=None, files=None):
    merged_counts = {
        "durable_topics": 1,
        "working_contexts": 0,
        "session_files": 0,
        "run_files": 0,
    }
    merged_counts.update(counts or {})
    manifest = {
        "schema_version": "memory-pack-v1",
        "created_at": "2026-05-05T00:00:00Z",
        "pack_id": "memory-pack-test",
        "repo_harness_version": "0.1.0",
        "preset": preset,
        "modules": list(modules),
        "source": {
            "workspace_fingerprint": "test-fingerprint",
            "cwd_hint": "test-workspace",
        },
        "counts": merged_counts,
        "warnings": list(warnings or []),
    }
    if files is not None:
        manifest["files"] = list(files)
    return manifest


def write_durable_memory(workspace_root, notes=None):
    notes = notes or [
        "Use constrained tools instead of guessing.",
        "Preserve local agent state under .repo-harness/.",
    ]
    memory_root = workspace_root / ".repo-harness" / "memory"
    topics_dir = memory_root / "topics"
    topics_dir.mkdir(parents=True)
    (memory_root / "MEMORY.md").write_text(
        "# Durable Memory Index\n\n"
        "- [project-conventions](topics/project-conventions.md): Project Conventions\n"
        "  - summary: Stable repository conventions.\n"
        "  - tags: convention\n",
        encoding="utf-8",
    )
    (topics_dir / "project-conventions.md").write_text(
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-05-05T00:00:00+00:00\n\n"
        "## Notes\n"
        + "\n".join(f"- {note}" for note in notes)
        + "\n",
        encoding="utf-8",
    )


def write_session(workspace_root, session_id="session-source", task_summary="Continue source task"):
    session_path = workspace_root / ".repo-harness" / "sessions" / f"{session_id}.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        json.dumps(
            {
                "id": session_id,
                "history": [
                    {"role": "user", "content": "source prompt"},
                    {"role": "assistant", "content": "source answer"},
                ],
                "memory": {
                    "working": {
                        "task_summary": task_summary,
                        "recent_files": ["README.md"],
                    },
                    "episodic_notes": [
                        {
                            "text": "Current blocker is validating memory pack import.",
                            "tags": ["memory-pack"],
                            "source": "session",
                            "created_at": "2026-05-05T00:00:00+00:00",
                            "note_index": 0,
                            "kind": "episodic",
                        }
                    ],
                    "file_summaries": {
                        "README.md": {
                            "summary": "README describes RepoHarness usage.",
                            "created_at": "2026-05-05T00:00:00+00:00",
                            "freshness": "sha256:test",
                        }
                    },
                    "task": task_summary,
                    "files": ["README.md"],
                    "notes": ["Current blocker is validating memory pack import."],
                    "next_note_index": 1,
                },
                "checkpoints": {
                    "current_id": "ckpt-source",
                    "items": {"ckpt-source": {"checkpoint_id": "ckpt-source"}},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return session_path


def write_run_artifacts(workspace_root, run_id="run-source"):
    run_dir = workspace_root / ".repo-harness" / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "trace.jsonl").write_text(
        json.dumps({"event": "model_prompt", "prompt": "source prompt with local paths"}) + "\n"
        + json.dumps({"event": "tool_executed", "output": "source tool output"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.json").write_text(
        json.dumps({"run_id": run_id, "summary": "source report"}, indent=2),
        encoding="utf-8",
    )
    return run_dir


def payload_entry(name, content):
    data = content if isinstance(content, bytes) else str(content).encode("utf-8")
    parts = name.split("/")
    return {
        "module": parts[1] if len(parts) > 1 and parts[0] == "payload" else "",
        "path": name,
        "sha256": hashlib_sha256(data),
        "size": len(data),
        "source_path": name.removeprefix("payload/"),
    }


def hashlib_sha256(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


def write_pack(pack_path, manifest=None, members=None):
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    encoded_members = {
        name: content if isinstance(content, bytes) else str(content).encode("utf-8")
        for name, content in (members or {}).items()
    }
    if manifest is not None:
        manifest = dict(manifest)
        manifest.setdefault(
            "files",
            [
                payload_entry(name, data)
                for name, data in encoded_members.items()
                if name.startswith("payload/") and not name.endswith("/")
            ],
        )
    with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if manifest is not None:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
        for name, content in encoded_members.items():
            archive.writestr(name, content)
    return pack_path


def zip_names(pack_path):
    with zipfile.ZipFile(pack_path) as archive:
        return set(archive.namelist())


def read_json_member(pack_path, member_name):
    with zipfile.ZipFile(pack_path) as archive:
        return json.loads(archive.read(member_name).decode("utf-8"))


def read_manifest(pack_path):
    return read_json_member(pack_path, MANIFEST_NAME)


def result_pack_path(result, fallback):
    if isinstance(result, (str, Path)):
        return Path(result)
    if isinstance(result, dict):
        return Path(result.get("pack_path") or result.get("path") or fallback)
    return Path(fallback)


def load_import_report(result, workspace_root):
    if isinstance(result, dict):
        return result
    report_dir = workspace_root / ".repo-harness" / "memory" / "imports"
    reports = sorted(report_dir.glob("import-*.json"))
    assert reports
    return json.loads(reports[-1].read_text(encoding="utf-8"))


def assert_member_under_payload(names, suffix):
    assert any(name.startswith("payload/") and name.endswith(suffix) for name in names)


def test_safe_transfer_export_contains_only_durable_memory(tmp_path):
    api = memory_pack_api()
    write_durable_memory(tmp_path)
    review_queue = tmp_path / ".repo-harness" / "memory" / "review-queue.jsonl"
    review_queue.write_text(
        json.dumps(
            {
                "schema_version": "durable-review-queue-v1",
                "id": "dmq-test",
                "created_at": "2026-05-12T00:00:00+00:00",
                "topic": "project-conventions",
                "text": "Pending candidates are not exported.",
                "source": {"run_id": "run-test"},
                "status": "pending",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    write_session(tmp_path)
    write_run_artifacts(tmp_path)

    pack_path = tmp_path / "safe-transfer.zip"
    result = api.export_memory_pack(
        repo_root=tmp_path,
        output_path=pack_path,
        preset="safe-transfer",
    )

    pack_path = result_pack_path(result, pack_path)
    assert pack_path.exists()
    manifest = read_manifest(pack_path)
    names = zip_names(pack_path)

    assert manifest["schema_version"] == "memory-pack-v1"
    assert manifest["preset"] == "safe-transfer"
    assert manifest["modules"] == ["durable_knowledge"]
    assert str(tmp_path) not in json.dumps(manifest)
    assert not Path(manifest["source"]["cwd_hint"]).is_absolute()
    assert manifest["counts"]["durable_topics"] == 1
    assert manifest["counts"]["session_files"] == 0
    assert manifest["counts"]["run_files"] == 0
    assert MANIFEST_NAME in names
    assert_member_under_payload(names, "durable_knowledge/MEMORY.md")
    assert_member_under_payload(names, "durable_knowledge/topics/project-conventions.md")
    assert not any("review-queue" in name for name in names)
    assert not any("/sessions/" in name or name.startswith("payload/resume_state/") for name in names)
    assert not any("/runs/" in name or name.startswith("payload/run_artifacts/") for name in names)
    assert not any("working_context" in name for name in names)


def test_continue_work_exports_working_context_without_overwriting_current_session(tmp_path):
    api = memory_pack_api()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    write_durable_memory(source)
    write_session(source, task_summary="Continue source memory-pack task")
    write_durable_memory(target, notes=["Target already has stable memory."])
    current_session = write_session(target, session_id="current-session", task_summary="Keep target task untouched")

    pack_path = tmp_path / "continue-work.zip"
    api.export_memory_pack(
        repo_root=source,
        output_path=pack_path,
        preset="continue-work",
    )

    manifest = read_manifest(pack_path)
    names = zip_names(pack_path)
    assert manifest["preset"] == "continue-work"
    assert manifest["modules"] == ["durable_knowledge", "working_context"]
    assert WORKING_CONTEXT_MEMBER in names
    exported_context = read_json_member(pack_path, WORKING_CONTEXT_MEMBER)
    assert exported_context["memory"]["working"]["task_summary"] == "Continue source memory-pack task"

    before_import = current_session.read_text(encoding="utf-8")
    api.import_memory_pack(target, pack_path)

    assert current_session.read_text(encoding="utf-8") == before_import
    snapshots = sorted((target / ".repo-harness" / "memory" / "imported-working-contexts").glob("*.json"))
    assert snapshots
    imported_context = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    assert imported_context["memory"]["working"]["task_summary"] == "Continue source memory-pack task"


def test_full_recovery_export_includes_sessions_runs_and_privacy_warning(tmp_path):
    api = memory_pack_api()
    write_durable_memory(tmp_path)
    write_session(tmp_path)
    write_run_artifacts(tmp_path)

    pack_path = tmp_path / "full-recovery.zip"
    api.export_memory_pack(
        repo_root=tmp_path,
        output_path=pack_path,
        preset="full-recovery",
    )

    manifest = read_manifest(pack_path)
    names = zip_names(pack_path)
    warning_text = " ".join(manifest["warnings"]).lower()

    assert manifest["preset"] == "full-recovery"
    assert manifest["modules"] == [
        "durable_knowledge",
        "working_context",
        "resume_state",
        "run_artifacts",
    ]
    assert manifest["counts"]["session_files"] == 1
    assert manifest["counts"]["run_files"] >= 2
    assert_member_under_payload(names, "resume_state/sessions/session-source.json")
    assert_member_under_payload(names, "run_artifacts/runs/run-source/trace.jsonl")
    assert_member_under_payload(names, "run_artifacts/runs/run-source/report.json")
    for required in ("prompts", "tool outputs", "local paths", "reports", "traces"):
        assert required in warning_text


@pytest.mark.parametrize(
    ("pack_name", "manifest", "members", "expected_error"),
    [
        ("missing-manifest.zip", None, {}, "manifest"),
        (
            "bad-schema.zip",
            {**baseline_manifest(), "schema_version": "memory-pack-v0"},
            {"payload/durable_knowledge/MEMORY.md": "# Durable Memory Index\n"},
            "schema",
        ),
        (
            "missing-payload.zip",
            baseline_manifest(
                modules=("durable_knowledge",),
                files=[payload_entry("payload/durable_knowledge/MEMORY.md", "# Durable Memory Index\n")],
            ),
            {},
            "payload",
        ),
        (
            "path-traversal.zip",
            baseline_manifest(),
            {
                "payload/durable_knowledge/MEMORY.md": "# Durable Memory Index\n",
                "payload/durable_knowledge/../escape.txt": "escape\n",
            },
            "path",
        ),
        (
            "bad-topic-slug.zip",
            baseline_manifest(
                files=[
                    payload_entry(
                        "payload/durable_knowledge/topics/project-conventions.md",
                        "# Project Conventions\n\n- topic: ../escape\n\n## Notes\n- unsafe\n",
                    )
                ],
            ),
            {
                "payload/durable_knowledge/topics/project-conventions.md": (
                    "# Project Conventions\n\n"
                    "- topic: ../escape\n\n"
                    "## Notes\n"
                    "- unsafe\n"
                ),
            },
            "topic slug",
        ),
    ],
)
def test_validate_and_import_reject_invalid_memory_packs(tmp_path, pack_name, manifest, members, expected_error):
    api = memory_pack_api()
    pack_path = write_pack(tmp_path / pack_name, manifest=manifest, members=members)
    error_type = getattr(api, "MemoryPackError", ValueError)

    with pytest.raises(error_type, match=f"(?i){re.escape(expected_error)}"):
        api.validate_memory_pack(pack_path)
    with pytest.raises(ValueError, match=f"(?i){re.escape(expected_error)}"):
        api.import_memory_pack(tmp_path / "target", pack_path)


def test_inspect_returns_manifest_counts_modules_and_warnings(tmp_path):
    api = memory_pack_api()
    manifest = baseline_manifest(
        preset="full-recovery",
        modules=("durable_knowledge", "working_context", "resume_state", "run_artifacts"),
        counts={"session_files": 1, "run_files": 2},
        warnings=["Full recovery may include prompts, tool outputs, local paths, reports, and traces."],
    )
    pack_path = write_pack(
        tmp_path / "inspectable.zip",
        manifest=manifest,
        members={
            "payload/durable_knowledge/MEMORY.md": "# Durable Memory Index\n",
            "payload/durable_knowledge/topics/project-conventions.md": "# Project Conventions\n",
            WORKING_CONTEXT_MEMBER: json.dumps(
                {
                    "schema_version": "working-context-v1",
                    "session_id": "session-source",
                    "source_session_path": ".repo-harness/sessions/session-source.json",
                    "memory": {"working": {"task_summary": "Inspect me"}},
                }
            ),
            "payload/resume_state/sessions/session-source.json": "{}",
            "payload/run_artifacts/runs/run-source/report.json": "{}",
            "payload/run_artifacts/runs/run-source/trace.jsonl": "",
        },
    )

    inspected = api.inspect_memory_pack(pack_path)

    assert inspected["manifest"]["preset"] == "full-recovery"
    assert inspected["manifest"]["modules"] == [
        "durable_knowledge",
        "working_context",
        "resume_state",
        "run_artifacts",
    ]
    assert inspected["manifest"]["counts"]["session_files"] == 1
    assert inspected["warnings"] == manifest["warnings"]
    assert inspected["ok"] is True


def test_conservative_import_skips_duplicate_note_and_existing_files(tmp_path):
    api = memory_pack_api()
    target = tmp_path / "target"
    target.mkdir()
    write_durable_memory(target, notes=["Use constrained tools instead of guessing."])
    existing_session = write_session(target, session_id="session-existing", task_summary="Existing target task")
    existing_session.write_text("current session must not be overwritten\n", encoding="utf-8")
    pack_topic = (
        "# Project Conventions\n\n"
        "- topic: project-conventions\n"
        "- summary: Stable repository conventions.\n"
        "- tags: convention\n"
        "- updated_at: 2026-05-05T00:00:00+00:00\n\n"
        "## Notes\n"
        "- Use constrained tools instead of guessing.\n"
        "- Prefer pytest tmp_path fixtures for pack tests.\n"
    )
    pack_path = write_pack(
        tmp_path / "merge.zip",
        manifest=baseline_manifest(
            preset="full-recovery",
            modules=("durable_knowledge", "resume_state"),
            counts={"session_files": 1},
        ),
        members={
            "payload/durable_knowledge/MEMORY.md": (
                "# Durable Memory Index\n\n"
                "- [project-conventions](topics/project-conventions.md): Project Conventions\n"
                "  - summary: Stable repository conventions.\n"
                "  - tags: convention\n"
            ),
            "payload/durable_knowledge/topics/project-conventions.md": pack_topic,
            "payload/resume_state/sessions/session-existing.json": "packed session should be skipped\n",
        },
    )

    result = api.import_memory_pack(target, pack_path)

    topic_text = (target / ".repo-harness" / "memory" / "topics" / "project-conventions.md").read_text(encoding="utf-8")
    assert topic_text.count("Use constrained tools instead of guessing.") == 1
    assert "Prefer pytest tmp_path fixtures for pack tests." in topic_text
    assert existing_session.read_text(encoding="utf-8") == "current session must not be overwritten\n"

    report = load_import_report(result, target)
    assert report["imported"]["durable_duplicate_notes_skipped"] == 1
    assert any("Use constrained tools instead of guessing." in note for note in report["skipped"]["duplicate_durable_notes"])
    assert any("sessions/session-existing.json" in path for path in report["skipped"]["existing_files"])


def test_validate_rejects_topic_file_name_that_disagrees_with_topic_slug(tmp_path):
    api = memory_pack_api()
    content = (
        "# Key Decisions\n\n"
        "- topic: key-decisions\n"
        "\n"
        "## Notes\n"
        "- Keep memory deterministic.\n"
    )
    pack_path = write_pack(
        tmp_path / "topic-mismatch.zip",
        manifest=baseline_manifest(
            files=[
                payload_entry(
                    "payload/durable_knowledge/topics/project-conventions.md",
                    content,
                )
            ],
        ),
        members={"payload/durable_knowledge/topics/project-conventions.md": content},
    )

    with pytest.raises(api.MemoryPackError, match="topic file name"):
        api.validate_memory_pack(pack_path)
    with pytest.raises(api.MemoryPackError, match="topic file name"):
        api.import_memory_pack(tmp_path / "target", pack_path)


def test_validate_rejects_invalid_working_context_payload(tmp_path):
    api = memory_pack_api()
    pack_path = write_pack(
        tmp_path / "bad-working-context.zip",
        manifest=baseline_manifest(
            preset="continue-work",
            modules=("working_context",),
            files=[payload_entry(WORKING_CONTEXT_MEMBER, "not json")],
        ),
        members={WORKING_CONTEXT_MEMBER: "not json"},
    )

    with pytest.raises(api.MemoryPackError, match="working context"):
        api.validate_memory_pack(pack_path)
    with pytest.raises(api.MemoryPackError, match="working context"):
        api.import_memory_pack(tmp_path / "target", pack_path)


def test_validate_rejects_duplicate_zip_payload_entries(tmp_path):
    api = memory_pack_api()
    pack_path = tmp_path / "duplicate-entry.zip"
    first = b"# Durable Memory Index\n"
    second = b"# Other\n"
    manifest = baseline_manifest(
        files=[payload_entry("payload/durable_knowledge/MEMORY.md", second)],
    )
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            archive.writestr("payload/durable_knowledge/MEMORY.md", first)
            archive.writestr("payload/durable_knowledge/MEMORY.md", second)

    with pytest.raises(api.MemoryPackError, match="duplicate archive entry"):
        api.validate_memory_pack(pack_path)


def test_export_skips_symlinked_state_files_that_escape_workspace(tmp_path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not supported on this platform")
    api = memory_pack_api()
    outside = tmp_path / "outside-session.json"
    outside.write_text('{"secret":"outside"}\n', encoding="utf-8")
    sessions_root = tmp_path / ".repo-harness" / "sessions"
    sessions_root.mkdir(parents=True)
    symlink_path = sessions_root / "linked.json"
    try:
        symlink_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation is not permitted: {exc}")

    pack_path = tmp_path / "resume.zip"
    result = api.export_memory_pack(
        tmp_path,
        output_path=pack_path,
        modules=("resume_state",),
    )

    assert result["counts"]["session_files"] == 0
    assert "Skipped symlinked state file" in " ".join(result["warnings"])
    with zipfile.ZipFile(pack_path) as archive:
        assert "payload/resume_state/sessions/linked.json" not in archive.namelist()
