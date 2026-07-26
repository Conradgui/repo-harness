"""Print the permission decision for every write scenario, on any branch.

This is the evidence behind the decision to abandon the codex branch
(docs/decisions/001). That branch's agent could not modify a file under any
configuration; this branch's can, under the configurations that should allow
it. The claim was originally made from an uncommitted script, which made the
single most load-bearing figure in the delivery package the least
reproducible thing in the repository.

To compare two refs, use a worktree and pin PYTHONPATH to it:

    git worktree add --detach /tmp/other <ref>
    cp scripts/permission_probe.py /tmp/other/scripts/
    PYTHONPATH=/tmp/other python scripts/permission_probe.py

Without PYTHONPATH the editable install resolves `repo_harness` back to the
main working tree, and the probe silently measures the branch you are already
on. It reports the module path it loaded so this is visible; check it.

Exit code is 0 if at least one scenario allows a write, 1 if none do -- so a
branch where the agent cannot write anything fails the probe outright.

Measured 2026-07-27: rebuild/trunk allows 6 of 14, and
codex/repo-harness-phase1-security-kernel allows 0 of 14, every one of them
denied with `file_mutation_disabled`.
"""

import sys
import tempfile
from pathlib import Path

from repo_harness.permissions import PermissionChecker
from repo_harness.tools import BASE_TOOL_SPECS

# Both mutating tools, across every configuration that governs them.
TOOLS = ("write_file", "patch_file")

SCENARIOS = (
    ("default (approval=ask)", {}),
    ("approval=auto", {"approval_policy": "auto"}),
    ("approval=never", {"approval_policy": "never"}),
    ("read_only=True", {"read_only": True}),
    ("write_scope matches", {"write_scope": ("src",)}),
    ("write_scope mismatch", {"write_scope": ("docs",)}),
    ("plan mode", {"runtime_mode": "plan", "active_plan_path": "plan.md"}),
)


class ProbeRuntime:
    """Minimal stand-in exposing only what PermissionChecker reads."""

    def __init__(self, root, **kw):
        self.root = Path(root)
        self.tools = BASE_TOOL_SPECS
        self.active_tool_profile = None
        self.tool_profile = "default"
        self.runtime_mode = kw.get("runtime_mode", "default")
        self.write_scope = kw.get("write_scope", ())
        self.read_only = kw.get("read_only", False)
        self.approval_policy = kw.get("approval_policy", "ask")
        self.active_plan_path = kw.get("active_plan_path", "")

    def path(self, raw):
        return (self.root / str(raw)).resolve()


def main():
    import repo_harness

    print(f"repo_harness loaded from: {repo_harness.__file__}\n")
    root = Path(tempfile.mkdtemp(prefix="rh-probe-"))
    (root / "src").mkdir(exist_ok=True)

    rows = []
    for label, kwargs in SCENARIOS:
        for tool in TOOLS:
            checker = PermissionChecker(ProbeRuntime(root, **kwargs))
            decision = checker.check(tool, {"path": "src/app.py"})
            rows.append((f"{label} / {tool}", decision.decision, decision.reason))

    width = max(len(r[0]) for r in rows)
    print(f"{'scenario'.ljust(width)}  decision  reason")
    print("-" * (width + 28))
    for label, decision, reason in rows:
        print(f"{label.ljust(width)}  {decision:8}  {reason}")

    allowed = [r for r in rows if r[1] == "allow"]
    print(f"\nwrite allowed in {len(allowed)} of {len(rows)} scenarios")
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
