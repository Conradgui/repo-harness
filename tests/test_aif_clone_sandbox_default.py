"""AIF 外部 clone 的受限沙箱默认与 bubblewrap 网络隔离（finding: clone-sandbox-default-off）。

此前无沙箱声明的 clone 通过 sandbox_config_for_directory 拿到 mode="off"
默认，叠加 AIF runner 的 approval_policy="auto"，模型命令既无沙箱也无审批
直接执行；bubblewrap argv 也没有网络隔离参数，即便配置了沙箱出网仍然可能。
"""

import shutil
import subprocess
from unittest.mock import patch

from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.auto_issue_fix.config import AutoIssueFixConfig, AutoIssueFixIssue
from repo_harness.auto_issue_fix.runner import (
    UNDECLARED_CLONE_SANDBOX,
    run_repoharness_fix_turn,
)
from repo_harness.sandbox import SandboxConfig

TOOL_CALL = (
    '<tool>{"name":"run_shell","args":'
    '{"command":"echo pwned > pwned.txt","timeout":20}}</tool>'
)
FINAL = "<final>done</final>"
SESSIONS_SUBDIR = (".repo-harness", "sessions")


def _issue():
    return AutoIssueFixIssue(repo="owner/name", number=1, title="t", body="b", url="u")


def _config():
    return AutoIssueFixConfig(repo="owner/name", issue=1)


def _wiring_agent(monkeypatch, seen):
    class FakeAgent:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def ask(self, prompt):
            del prompt
            return "done"

    monkeypatch.setattr("repo_harness.runtime.RepoHarness", FakeAgent)


def _session_events_text(clone_dir):
    from pathlib import Path

    sessions = Path(clone_dir) / SESSIONS_SUBDIR[0] / SESSIONS_SUBDIR[1]
    chunks = []
    for path in sorted(sessions.glob("*.events.jsonl")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


# --- AIF wiring：无声明 clone 的受限默认 ---


def test_undeclared_clone_gets_restricted_sandbox_default(tmp_path, monkeypatch):
    """无沙箱声明的 clone：AIF 默认受限沙箱（required + bubblewrap + 无网络）。"""
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    seen = {}
    _wiring_agent(monkeypatch, seen)

    run_repoharness_fix_turn(_config(), _issue(), tmp_path, model_client=object())

    config = seen["sandbox_config"]
    assert config.mode == "required"
    assert config.backend == "bubblewrap"
    assert config.allow_network is False


def test_sandbox_section_without_mode_still_gets_fallback(tmp_path, monkeypatch):
    """对抗测试：只写 [sandbox] 段但不声明 mode 的残缺声明不是 mode 声明。

    旧判定把“段存在”当“已声明”，一个 `[sandbox] workspace_write = true`
    的 clone 就能绕过受限默认拿到 mode=off 裸跑。
    """
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    (tmp_path / ".repo-harness.toml").write_text(
        "[sandbox]\nworkspace_write = true\n", encoding="utf-8"
    )
    seen = {}
    _wiring_agent(monkeypatch, seen)

    run_repoharness_fix_turn(_config(), _issue(), tmp_path, model_client=object())

    assert seen["sandbox_config"].mode == "required"
    assert seen["sandbox_config"].backend == "bubblewrap"


def test_declared_mode_off_is_still_honoured(tmp_path, monkeypatch):
    """clone 显式声明 mode="off" 时尊重显式配置（行为不变）。"""
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    (tmp_path / ".repo-harness.toml").write_text(
        '[sandbox]\nmode = "off"\n', encoding="utf-8"
    )
    seen = {}
    _wiring_agent(monkeypatch, seen)

    run_repoharness_fix_turn(_config(), _issue(), tmp_path, model_client=object())

    assert seen["sandbox_config"].mode == "off"


def test_undeclared_clone_fallback_constant_is_fail_safe():
    """受限默认本身 fail-safe：required 模式保证后端不可用时拒绝执行。"""
    assert UNDECLARED_CLONE_SANDBOX.mode == "required"
    assert UNDECLARED_CLONE_SANDBOX.allow_network is False


# --- bubblewrap argv：网络隔离 ---


def _bwrap_agent(tmp_path, sandbox_config):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        sandbox_config=sandbox_config,
    )


def _capture_bwrap_argv(agent):
    captured = {}
    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv and str(argv[0]) == "/usr/bin/bwrap":
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="sandboxed ok", stderr="")
        return real_run(argv, **kwargs)

    agent.sandbox_runner.which = lambda name: "/usr/bin/bwrap"
    with patch("repo_harness.sandbox.subprocess.run", fake_run):
        result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})
    return captured["argv"], result


def test_bubblewrap_argv_blocks_network_by_default(tmp_path):
    """bubblewrap 沙箱默认断网：--unshare-net 必须在 argv 里。"""
    agent = _bwrap_agent(
        tmp_path, SandboxConfig(mode="required", backend="bubblewrap")
    )

    argv, result = _capture_bwrap_argv(agent)

    assert argv[0] == "/usr/bin/bwrap"
    assert "--unshare-net" in argv
    assert "exit_code: 0" in result


def test_bubblewrap_argv_allows_network_when_configured(tmp_path):
    """allow_network=true 是唯一的显式出网开关。"""
    agent = _bwrap_agent(
        tmp_path,
        SandboxConfig(mode="required", backend="bubblewrap", allow_network=True),
    )

    argv, _ = _capture_bwrap_argv(agent)

    assert "--unshare-net" not in argv


def test_toml_allow_network_is_resolved(tmp_path):
    from repo_harness.config import sandbox_config_for_directory

    (tmp_path / ".repo-harness.toml").write_text(
        '[sandbox]\nmode = "required"\nbackend = "bubblewrap"\nallow_network = true\n',
        encoding="utf-8",
    )

    assert sandbox_config_for_directory(tmp_path).allow_network is True


# --- 端到端：AIF 修复 turn 对模型命令的默认防线 ---


def test_aif_fix_turn_on_undeclared_clone_blocks_shell_without_backend(tmp_path, monkeypatch):
    """对抗测试：无配置 clone + 沙箱后端不可用 → 模型命令被拒绝而非裸跑。"""
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    answer = run_repoharness_fix_turn(
        _config(),
        _issue(),
        tmp_path,
        model_client=FakeModelClient([TOOL_CALL, FINAL]),
    )

    assert answer == "done"
    assert not (tmp_path / "pwned.txt").exists()
    events = _session_events_text(tmp_path)
    assert "sandbox_unavailable" in events
    assert '"tool_error_code": "tool_failed"' in events


def test_aif_fix_turn_routes_shell_through_bubblewrap(tmp_path, monkeypatch):
    """对抗测试：沙箱可用时模型命令默认经过 bubblewrap 且无网络。"""
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    captured = {}
    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        argv = list(argv)
        if argv and str(argv[0]) == "/usr/bin/bwrap":
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="sandboxed ok", stderr="")
        return real_run(argv, **kwargs)

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.setattr("repo_harness.sandbox.subprocess.run", fake_run)

    answer = run_repoharness_fix_turn(
        _config(),
        _issue(),
        tmp_path,
        model_client=FakeModelClient([TOOL_CALL, FINAL]),
    )

    assert answer == "done"
    assert captured["argv"][0] == "/usr/bin/bwrap"
    assert "--unshare-net" in captured["argv"]
    # 命令没有落到宿主机 shell：echo 的副作用不存在。
    assert not (tmp_path / "pwned.txt").exists()
