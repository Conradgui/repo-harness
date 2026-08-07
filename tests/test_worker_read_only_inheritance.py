"""A child worker must never be more privileged than its parent.

If a read_only parent (e.g. Auto Issue Fix on a clone that declared
sandbox=read_only) could spawn a writable worker, the model could bypass the
declared boundary through the worker's write_file/patch_file. The child's
read_only must be the parent's OR the Explore default.
"""

from repo_harness.core.worker_runtime import build_child_runtime
from tests.conftest import build_agent


def test_read_only_parent_forces_read_only_worker(tmp_path):
    parent = build_agent(tmp_path, [], read_only=True)
    child = build_child_runtime(parent, "worker", write_scope=["src"])
    assert child.read_only is True, (
        "a worker of a read-only parent must stay read-only (no privilege escalation)"
    )


def test_writable_parent_allows_writable_worker(tmp_path):
    parent = build_agent(tmp_path, [], read_only=False)
    child = build_child_runtime(parent, "worker", write_scope=["src"])
    assert child.read_only is False, "a worker of a writable parent may write within scope"


def test_explore_child_always_read_only_even_from_writable_parent(tmp_path):
    parent = build_agent(tmp_path, [], read_only=False)
    child = build_child_runtime(parent, "Explore", write_scope=None)
    assert child.read_only is True, "Explore children are always read-only"
