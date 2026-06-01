from repo_harness import FakeModelClient, RepoHarness, SessionStore, WorkspaceContext
from repo_harness.sandbox import SandboxConfig


def build_agent(tmp_path, sandbox_config):
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    return RepoHarness(
        model_client=FakeModelClient([]),
        workspace=WorkspaceContext.build(tmp_path),
        session_store=SessionStore(tmp_path / ".repo-harness" / "sessions"),
        approval_policy="auto",
        sandbox_config=sandbox_config,
    )


def test_required_sandbox_does_not_honor_excluded_commands(tmp_path):
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="required", backend="bubblewrap", excluded_commands=("echo*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "echo hi", "timeout": 20})

    assert "sandbox required but unavailable" in result


def test_best_effort_excluded_commands_support_glob_patterns(tmp_path):
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("python*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "python --version", "timeout": 20})

    assert "sandbox_unavailable" not in agent.session_event_bus.path.read_text(encoding="utf-8")
    assert "exit_code:" in result


def test_excluded_commands_not_bypassed_by_leading_whitespace(tmp_path):
    """Leading whitespace must not prevent excluded_commands from matching."""
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("echo*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    result = agent.run_tool("run_shell", {"command": "  echo hi", "timeout": 20})

    # 应被排除(不走 sandbox)，直接运行成功
    assert "sandbox_unavailable" not in agent.session_event_bus.path.read_text(encoding="utf-8")
    assert "exit_code:" in result


def test_excluded_commands_not_bypassed_by_shell_metacharacters(tmp_path):
    """Shell metacharacters must not bypass excluded_commands to skip sandbox."""
    agent = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("echo*",)),
    )
    agent.sandbox_runner.which = lambda name: None

    # 命令替换 $(echo) 不应跳过 sandbox，应触发 sandbox_unavailable
    agent.run_tool("run_shell", {"command": "$(echo cat) /etc/passwd", "timeout": 20})
    assert "sandbox_unavailable" in agent.session_event_bus.path.read_text(encoding="utf-8")

    # 反斜杠转义 \echo 不应跳过 sandbox
    agent2 = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("echo*",)),
    )
    agent2.sandbox_runner.which = lambda name: None
    agent2.run_tool("run_shell", {"command": "\\echo hi", "timeout": 20})
    assert "sandbox_unavailable" in agent2.session_event_bus.path.read_text(encoding="utf-8")

    # 变量展开 ${x} 不应跳过 sandbox
    agent3 = build_agent(
        tmp_path,
        SandboxConfig(mode="best_effort", backend="bubblewrap", excluded_commands=("cat*",)),
    )
    agent3.sandbox_runner.which = lambda name: None
    agent3.run_tool("run_shell", {"command": "${x}cat /etc/passwd", "timeout": 20})
    assert "sandbox_unavailable" in agent3.session_event_bus.path.read_text(encoding="utf-8")

