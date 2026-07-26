"""工具定义与执行辅助逻辑。

可以把这个文件看成 agent 的能力白名单：模型能申请哪些动作、这些动作
如何做参数校验，以及最终如何执行，都是在这里定义的。
"""

import os
import shutil
import subprocess
import textwrap
from functools import partial

from ..workspace import IGNORED_PATH_NAMES, clip
from .base import RegisteredTool

BASE_TOOL_SPECS = {
    "list_files": {
        "schema": {"path": "str='.'"},
        "risky": False,
        "description": "List files in the workspace.",
    },
    "read_file": {
        "schema": {"path": "str", "start": "int=1", "end": "int=200"},
        "risky": False,
        "description": "Read a UTF-8 file by line range.",
    },
    "search": {
        "schema": {"pattern": "str", "path": "str='.'"},
        "risky": False,
        "description": "Search the workspace with rg or a simple fallback.",
    },
    "run_shell": {
        "schema": {"command": "str", "timeout": "int=20"},
        "risky": True,
        "description": "Run a shell command in the repo root.",
    },
    "write_file": {
        "schema": {"path": "str", "content": "str"},
        "risky": True,
        "description": "Write a text file.",
    },
    "patch_file": {
        "schema": {"path": "str", "old_text": "str", "new_text": "str"},
        "risky": True,
        "description": "Replace one exact text block in a file.",
    },
    "todo_add": {
        "schema": {"text": "str", "status": "str='pending'"},
        "risky": False,
        "description": "Add an item to the session todo ledger.",
    },
    "todo_update": {
        "schema": {"id": "str", "text": "str?", "status": "str?"},
        "risky": False,
        "description": "Update an item in the session todo ledger.",
    },
    "todo_list": {
        "schema": {},
        "risky": False,
        "description": "List the session todo ledger.",
    },
    "ask_user": {
        "schema": {"question": "str", "choices": "list=[]"},
        "risky": False,
        "description": "Ask the user a short question and record the answer.",
    },
    "agent": {
        "schema": {"task": "str", "type": "str='Explore'", "scope": "list=[]"},
        "risky": False,
        "description": "Spawn a bounded subagent worker.",
    },
    "send_message": {
        "schema": {"id": "str", "message": "str"},
        "risky": False,
        "description": "Send a message to an existing subagent.",
    },
    "task_stop": {
        "schema": {"id": "str"},
        "risky": False,
        "description": "Stop a subagent worker.",
    },
}

DELEGATE_TOOL_SPEC = {
    "schema": {"task": "str", "max_steps": "int=3"},
    "risky": False,
    "description": "Ask a bounded read-only child agent to investigate.",
}

TOOL_EXAMPLES = {
    "list_files": '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
    "read_file": '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":80}}</tool>',
    "search": '<tool>{"name":"search","args":{"pattern":"binary_search","path":"."}}</tool>',
    "run_shell": '<tool>{"name":"run_shell","args":{"command":"uv run --with pytest python -m pytest -q","timeout":20}}</tool>',
    "write_file": '<tool name="write_file" path="binary_search.py"><content>def binary_search(nums, target):\n    return -1\n</content></tool>',
    "patch_file": '<tool name="patch_file" path="binary_search.py"><old_text>return -1</old_text><new_text>return mid</new_text></tool>',
    "delegate": '<tool>{"name":"delegate","args":{"task":"inspect README.md","max_steps":3}}</tool>',
    "todo_add": '<tool>{"name":"todo_add","args":{"text":"Run tests","status":"pending"}}</tool>',
    "todo_update": '<tool>{"name":"todo_update","args":{"id":"todo_1","status":"completed"}}</tool>',
    "todo_list": '<tool>{"name":"todo_list","args":{}}</tool>',
    "ask_user": '<tool>{"name":"ask_user","args":{"question":"Proceed?","choices":["yes","no"]}}</tool>',
    "agent": '<tool>{"name":"agent","args":{"task":"inspect README","type":"Explore"}}</tool>',
    "send_message": '<tool>{"name":"send_message","args":{"id":"agent_1","message":"continue"}}</tool>',
    "task_stop": '<tool>{"name":"task_stop","args":{"id":"agent_1"}}</tool>',
}


def _preferred_shell_path():
    for candidate in (
        shutil.which("bash"),
        shutil.which("sh"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def build_tool_registry(agent):
    # 工具不是动态发现的，而是显式注册的。
    # 这样模型看到的是一个有边界、可审计的动作集合。
    tools = {
        name: RegisteredTool(
            name=name,
            schema=spec["schema"],
            description=spec["description"],
            risky=bool(spec["risky"]),
            runner=partial(_TOOL_RUNNERS[name], agent),
        )
        for name, spec in BASE_TOOL_SPECS.items()
    }
    # 子 agent 是刻意做成受限能力的：一旦深度耗尽，
    # 就连 delegate 这个工具都不再暴露给模型。
    if agent.depth < agent.max_depth:
        tools["delegate"] = RegisteredTool(
            name="delegate",
            schema=DELEGATE_TOOL_SPEC["schema"],
            description=DELEGATE_TOOL_SPEC["description"],
            risky=False,
            runner=partial(tool_delegate, agent),
        )
    return tools


def tool_example(name):
    return TOOL_EXAMPLES.get(name, "")


def validate_tool(agent, name, args):
    args = args or {}
    args = _normalize_tool_args(name, args)

    if name == "list_files":
        path = agent.path(args.get("path", "."))
        if not path.is_dir():
            raise ValueError("path is not a directory")
        return

    if name == "read_file":
        path = agent.path(args["path"])
        if not path.is_file():
            raise ValueError("path is not a file")
        start = int(args.get("start", 1))
        end = int(args.get("end", 200))
        if start < 1 or end < start:
            raise ValueError("invalid line range")
        return

    if name == "search":
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            raise ValueError("pattern must not be empty")
        agent.path(args.get("path", "."))
        return

    if name == "run_shell":
        command = str(args.get("command", "")).strip()
        if not command:
            raise ValueError("command must not be empty")
        timeout = int(args.get("timeout", 20))
        if timeout < 1 or timeout > 120:
            raise ValueError("timeout must be in [1, 120]")
        return

    if name == "write_file":
        path = agent.path(args["path"])
        if path.exists() and path.is_dir():
            raise ValueError("path is a directory")
        if "content" not in args:
            raise ValueError("missing content")
        return

    if name == "patch_file":
        # patch_file 故意做得很严格：old_text 必须精确命中且只能出现一次，
        # 这样修改行为才是确定的，失败原因也更容易解释。
        path = agent.path(args["path"])
        if not path.is_file():
            raise ValueError("path is not a file")
        old_text = str(args.get("old_text", ""))
        if not old_text:
            raise ValueError("old_text must not be empty")
        if "new_text" not in args:
            raise ValueError("missing new_text")
        text = path.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count != 1:
            raise ValueError(f"old_text must occur exactly once, found {count}")
        return

    if name == "todo_add":
        if not str(args.get("text", "")).strip():
            raise ValueError("text must not be empty")
        return

    if name == "todo_update":
        if not str(args.get("id", "")).strip():
            raise ValueError("id must not be empty")
        if "text" not in args and "status" not in args:
            raise ValueError("text or status is required")
        return

    if name == "todo_list":
        return

    if name == "ask_user":
        if not str(args.get("question", "")).strip():
            raise ValueError("question must not be empty")
        choices = args.get("choices", [])
        if choices is not None and not isinstance(choices, list):
            raise ValueError("choices must be a list")
        return

    if name == "agent":
        if not str(args.get("task", "")).strip():
            raise ValueError("task must not be empty")
        return

    if name == "send_message":
        if not str(args.get("id", "")).strip():
            raise ValueError("id must not be empty")
        if not str(args.get("message", "")).strip():
            raise ValueError("message must not be empty")
        return

    if name == "task_stop":
        if not str(args.get("id", "")).strip():
            raise ValueError("id must not be empty")
        return

    if name == "delegate":
        task = str(args.get("task", "")).strip()
        if not task:
            raise ValueError("task must not be empty")
        return


def tool_list_files(agent, args):
    path = agent.path(args.get("path", "."))
    if not path.is_dir():
        raise ValueError("path is not a directory")
    entries = [
        item for item in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        if item.name not in IGNORED_PATH_NAMES
    ]
    lines = []
    for entry in entries[:200]:
        kind = "[D]" if entry.is_dir() else "[F]"
        lines.append(f"{kind} {entry.relative_to(agent.root)}")
    return "\n".join(lines) or "(empty)"


def tool_read_file(agent, args):
    path = agent.path(args["path"])
    if not path.is_file():
        raise ValueError("path is not a file")
    start = int(args.get("start", 1))
    end = int(args.get("end", 200))
    if start < 1 or end < start:
        raise ValueError("invalid line range")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    body = "\n".join(f"{number:>4}: {line}" for number, line in enumerate(lines[start - 1:end], start=start))
    return f"# {path.relative_to(agent.root)}\n{body}"


def tool_search(agent, args):
    pattern = str(args.get("pattern", "")).strip()
    if not pattern:
        raise ValueError("pattern must not be empty")
    path = agent.path(args.get("path", "."))

    # smart-case：pattern 含大写时区分大小写，否则忽略。两条搜索路径共用这个判断，
    # 保证装没装 rg 的结果一致。
    case_sensitive = any(character.isupper() for character in pattern)

    if shutil.which("rg"):
        # 优先用 rg，因为搜索会非常频繁，搜索延迟会直接影响 agent 控制循环。
        # --fixed-strings 让 pattern 按字面匹配，语义与下面的 Python fallback 对齐，
        # 同时避免模型构造的正则触发 ReDoS。
        # -- 终止选项解析，否则以 - 开头的 pattern 会被 rg 当成选项执行。
        result = subprocess.run(
            [
                "rg", "-n", "--smart-case", "--fixed-strings", "--max-count", "200",
                "--", pattern, str(path),
            ],
            cwd=agent.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip() or result.stderr.strip() or "(no matches)"

    needle = pattern if case_sensitive else pattern.lower()
    matches = []
    files = [path] if path.is_file() else [
        item for item in path.rglob("*")
        if item.is_file() and not any(part in IGNORED_PATH_NAMES for part in item.relative_to(agent.root).parts)
    ]
    for file_path in files:
        for number, line in enumerate(file_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            haystack = line if case_sensitive else line.lower()
            if needle in haystack:
                matches.append(f"{file_path.relative_to(agent.root)}:{number}:{line}")
                if len(matches) >= 200:
                    return "\n".join(matches)
    return "\n".join(matches) or "(no matches)"


def tool_run_shell(agent, args):
    command = str(args.get("command", "")).strip()
    if not command:
        raise ValueError("command must not be empty")
    timeout = int(args.get("timeout", 20))
    if timeout < 1 or timeout > 120:
        raise ValueError("timeout must be in [1, 120]")
    shell_env = agent.shell_env()

    def platform_runner(command, timeout):
        result = subprocess.run(
            command,
            cwd=agent.root,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=shell_env,
        )
        return textwrap.dedent(
            f"""\
            exit_code: {result.returncode}
            stdout:
            {result.stdout.strip() or "(empty)"}
            stderr:
            {result.stderr.strip() or "(empty)"}
            """
        ).strip()

    sandbox_runner = getattr(agent, "sandbox_runner", None)
    if sandbox_runner is not None:
        sandbox_result = sandbox_runner.run(agent, command, timeout, platform_runner)
        if sandbox_result is not None:
            return sandbox_result

    bash_path = _preferred_shell_path()
    if bash_path:
        result = subprocess.run(
            [bash_path, "-lc", command],
            cwd=agent.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=shell_env,
        )
        return textwrap.dedent(
            f"""\
            exit_code: {result.returncode}
            stdout:
            {result.stdout.strip() or "(empty)"}
            stderr:
            {result.stderr.strip() or "(empty)"}
            """
        ).strip()
    result = subprocess.run(
        command,
        cwd=agent.root,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        # 这里传入的是过滤后的环境变量，而不是直接继承整个父 shell 环境，
        # 目的是减少敏感信息被意外带进命令执行环境的风险。
        env=shell_env,
    )
    return textwrap.dedent(
        f"""\
        exit_code: {result.returncode}
        stdout:
        {result.stdout.strip() or "(empty)"}
        stderr:
        {result.stderr.strip() or "(empty)"}
        """
    ).strip()


def tool_write_file(agent, args):
    path = agent.path(args["path"])
    content = str(args["content"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path.relative_to(agent.root).as_posix()} ({len(content)} chars)"


def tool_patch_file(agent, args):
    path = agent.path(args["path"])
    if not path.is_file():
        raise ValueError("path is not a file")
    old_text = str(args.get("old_text", ""))
    if not old_text:
        raise ValueError("old_text must not be empty")
    if "new_text" not in args:
        raise ValueError("missing new_text")
    text = path.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count != 1:
        raise ValueError(f"old_text must occur exactly once, found {count}")
    path.write_text(text.replace(old_text, str(args["new_text"]), 1), encoding="utf-8")
    return f"patched {path.relative_to(agent.root).as_posix()}"


def tool_delegate(agent, args):
    if agent.depth >= agent.max_depth:
        raise ValueError("delegate depth exceeded")
    task = str(args.get("task", "")).strip()
    if not task:
        raise ValueError("task must not be empty")

    from ..runtime import RepoHarness

    child = RepoHarness(
        model_client=agent.model_client,
        workspace=agent.workspace,
        session_store=agent.session_store,
        run_store=agent.run_store,
        approval_policy="never",
        max_steps=int(args.get("max_steps", 3)),
        max_new_tokens=agent.max_new_tokens,
        depth=agent.depth + 1,
        max_depth=agent.max_depth,
        read_only=True,
        secret_env_names=agent.secret_env_names,
        shell_env_allowlist=agent.shell_env_allowlist,
    )
    # 委派的目标是“调查”，不是“放权执行”。
    # 子 agent 以只读方式运行、步数更少，最后只把结论文本返回给父 agent。
    child.session["memory"]["task"] = task
    child.session["memory"]["notes"] = [clip(agent.history_text(), 300)]
    return "delegate_result:\n" + child.ask(task)


def tool_todo_add(agent, args):
    item = agent.todo_ledger.add(args.get("text", ""), status=args.get("status", "pending"))
    return f"added {item['id']}: {item['text']}"


def tool_todo_update(agent, args):
    item = agent.todo_ledger.update(args.get("id", ""), text=args.get("text"), status=args.get("status"))
    return f"updated {item['id']}: {item['status']} {item['text']}"


def tool_todo_list(agent, args):
    del args
    return agent.todo_ledger.render()


def tool_ask_user(agent, args):
    question = str(args.get("question", "")).strip()
    choices = [str(item) for item in (args.get("choices") or [])]
    callback = getattr(agent, "ask_user_callback", None)
    if callback is not None:
        answer = callback(question, choices)
    elif choices:
        answer = choices[0]
    else:
        try:
            answer = input(question + " ")
        except EOFError:
            answer = ""
    return f"answer: {answer}"


def tool_agent(agent, args):
    args = _normalize_tool_args("agent", args)
    scope = args.get("scope") or args.get("write_scope") or []
    result = agent.spawn_worker(
        args.get("task", ""),
        args.get("task", ""),
        subagent_type=args.get("type", "Explore"),
        write_scope=scope,
    )
    return f"{result['id']} {result['status']}: {result.get('result', '')}"


def tool_send_message(agent, args):
    args = _normalize_tool_args("send_message", args)
    result = agent.worker_manager.send(args.get("id", ""), args.get("message", ""))
    return f"{result['id']} {result['status']}: {result.get('result', '')}"


def tool_task_stop(agent, args):
    args = _normalize_tool_args("task_stop", args)
    result = agent.worker_manager.stop(args.get("id", ""))
    return f"{result['id']} {result['status']}"


_TOOL_RUNNERS = {
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "search": tool_search,
    "run_shell": tool_run_shell,
    "write_file": tool_write_file,
    "patch_file": tool_patch_file,
    "todo_add": tool_todo_add,
    "todo_update": tool_todo_update,
    "todo_list": tool_todo_list,
    "ask_user": tool_ask_user,
    "agent": tool_agent,
    "send_message": tool_send_message,
    "task_stop": tool_task_stop,
}


def _normalize_tool_args(name, args):
    args = dict(args or {})
    if name == "agent":
        if "description" in args and "task" not in args:
            args["task"] = args["description"]
        if "prompt" in args and "task" not in args:
            args["task"] = args["prompt"]
        if "subagent_type" in args and "type" not in args:
            args["type"] = args["subagent_type"]
        if "write_scope" in args and "scope" not in args:
            args["scope"] = args["write_scope"]
    if name == "todo_add" and "content" in args and "text" not in args:
        args["text"] = args["content"]
    if name == "todo_update":
        if "todo_id" in args and "id" not in args:
            args["id"] = args["todo_id"]
        if "content" in args and "text" not in args:
            args["text"] = args["content"]
    if name in {"send_message", "task_stop"}:
        if "task_id" in args and "id" not in args:
            args["id"] = args["task_id"]
        if "to" in args and "id" not in args:
            args["id"] = args["to"]
    return args

