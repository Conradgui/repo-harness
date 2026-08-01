"""Print the permission decision for every write scenario, on any branch.

This is the evidence behind the decision to abandon the codex branch
(docs/decisions/001). That branch's agent could not modify a file under any
configuration; this branch's can, under the configurations that should allow
it. The claim was originally made from an uncommitted script, which made the
single most load-bearing figure in the delivery package the least
reproducible thing in the repository.

To compare two refs, run it from a worktree with the editable install disabled:

    git worktree add --detach /tmp/other <ref>
    cp scripts/permission_probe.py /tmp/other/scripts/
    cd /tmp/other
    python -E -s scripts/permission_probe.py     # -s skips site-packages hooks

PYTHONPATH alone is not enough. The editable install registers a MetaPathFinder
via a .pth file, which runs before sys.path is consulted and resolves
`repo_harness` back to the main working tree regardless of PYTHONPATH. A run
that looks correct then silently measures the branch you are already on.

The probe prints the module path it loaded as its first line. **Read it.** If it
does not point inside the worktree, the numbers below it are meaningless.

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

# run_shell is governed by the sandbox mode rather than by write_scope.
SHELL_SCENARIOS = (
    ("sandbox off", {"sandbox_mode": "off"}),
    ("sandbox read_only", {"sandbox_mode": "read_only"}),
    ("sandbox best_effort", {"sandbox_mode": "best_effort"}),
)


class ProbeSandbox:
    def __init__(self, mode):
        self.mode = mode


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
        self.sandbox_config = ProbeSandbox(kw.get("sandbox_mode", "off"))

    def path(self, raw):
        return (self.root / str(raw)).resolve()


def main():
    import repo_harness

    loaded = Path(repo_harness.__file__).resolve()
    here = Path(__file__).resolve().parents[1]
    print(f"repo_harness loaded from: {loaded}")
    if here not in loaded.parents:
        print(
            f"WARNING: that is outside {here} -- an editable install has "
            "redirected the import and these results describe another tree.\n"
        )
    else:
        print()
    root = Path(tempfile.mkdtemp(prefix="rh-probe-"))
    (root / "src").mkdir(exist_ok=True)

    rows = []
    for label, kwargs in SCENARIOS:
        for tool in TOOLS:
            checker = PermissionChecker(ProbeRuntime(root, **kwargs))
            decision = checker.check(tool, {"path": "src/app.py"})
            rows.append((f"{label} / {tool}", decision.decision, decision.reason))

    for label, kwargs in SHELL_SCENARIOS:
        checker = PermissionChecker(ProbeRuntime(root, approval_policy="auto", **kwargs))
        decision = checker.check("run_shell", {"command": "echo hi"})
        rows.append((f"{label} / run_shell", decision.decision, decision.reason))

    width = max(len(r[0]) for r in rows)
    print(f"{'scenario'.ljust(width)}  decision  reason")
    print("-" * (width + 28))
    for label, decision, reason in rows:
        print(f"{label.ljust(width)}  {decision:8}  {reason}")

    write_rows = rows[: len(SCENARIOS) * len(TOOLS)]
    shell_rows = rows[len(SCENARIOS) * len(TOOLS):]
    write_allowed = [r for r in write_rows if r[1] == "allow"]
    shell_allowed = [r for r in shell_rows if r[1] == "allow"]

    print(f"\nwrite allowed in {len(write_allowed)} of {len(write_rows)} scenarios")
    print(f"shell allowed in {len(shell_allowed)} of {len(shell_rows)} scenarios")
    # A branch where nothing can be written is not a coding agent -- that is the
    # condition this probe exists to detect.
    return 0 if write_allowed else 1


if __name__ == "__main__":
    sys.exit(main())
