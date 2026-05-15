"""命令行入口。

这个模块负责把“用户怎么启动 RepoHarness”翻译成 runtime 能理解的对象：
解析参数、挑模型后端、构建工作区快照、恢复或新建 session，
最后进入 one-shot 或交互式循环。
"""

import argparse
import dataclasses
import inspect as inspectlib
import os
import shutil
import sys
import textwrap
from pathlib import Path

from . import memory as memorylib
from .models import AnthropicCompatibleModelClient, OllamaModelClient, OpenAICompatibleModelClient
from .runtime import RepoHarness, SessionStore
from .workspace import WorkspaceContext, middle

DEFAULT_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "OPENAI_API_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "RIGHT_CODES_API_KEY",
    "GITHUB_PAT",
    "GH_PAT",
)

WELCOME_ART = (
    "        /\\___/\\\\",
    "       (  o o  )",
    "       /   ^   \\\\",
    "      /|       |\\\\",
)
WELCOME_NAME = "RepoHarness"
WELCOME_SUBTITLE = "local repository harness"
WELCOME_STATUS = "calm shell, ready for work"
HELP_DETAILS = textwrap.dedent(
    """\
    Commands:
    /help    Show this help message.
    /memory  Show the agent's distilled working memory.
    /memory review  Review pending durable memory candidates.
    /memory self_iteration  Show the latest memory self-iteration status.
    /memory_explain <query>  Explain which memory notes match a query.
    /memory_pack  Export, import, inspect, or validate memory packs.
    /session Show the path to the saved session file.
    /reset   Clear the current session history and memory.
    /exit    Exit the agent.
    """
).strip()


DEFAULT_OLLAMA_MODEL = "qwen3.5:4b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENAI_BASE_URL = "https://www.right.codes/codex/v1"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_ANTHROPIC_BASE_URL = "https://www.right.codes/claude/v1"
SECRET_ENV_NAMES_VAR = "REPO_HARNESS_SECRET_ENV_NAMES"


def _effective_model(args, provider):
    # 模型选择优先级：
    # 1. 用户显式传入 --model
    # 2. provider 对应的环境变量
    # 3. 代码里的默认值
    explicit_model = getattr(args, "model", None)
    if explicit_model:
        return explicit_model
    if provider == "openai":
        model = os.environ.get("OPENAI_MODEL")
        if model:
            return model
        return DEFAULT_OPENAI_MODEL
    if provider == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL")
        if model:
            return model
        return DEFAULT_ANTHROPIC_MODEL
    return DEFAULT_OLLAMA_MODEL


def _first_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _configured_secret_names(args):
    configured_secret_names = set(DEFAULT_SECRET_ENV_NAMES)
    configured_secret_names.update(str(name).upper() for name in args.secret_env_names)
    extra_names = os.environ.get(SECRET_ENV_NAMES_VAR, "")
    if extra_names.strip():
        configured_secret_names.update(
            item.strip().upper()
            for item in extra_names.split(",")
            if item.strip()
        )
    return sorted(configured_secret_names)


def _load_memory_pack_api():
    try:
        from . import memory_pack
    except ImportError as exc:
        raise RuntimeError("memory pack support is unavailable: repo_harness.memory_pack could not be imported") from exc
    return memory_pack


def _call_memory_pack_function(function, aliases=None, **kwargs):
    aliases = aliases or {}
    try:
        signature = inspectlib.signature(function)
    except (TypeError, ValueError):
        return function(**kwargs)

    parameters = signature.parameters
    if any(parameter.kind == inspectlib.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return function(**kwargs)

    accepted = {}
    for key, value in kwargs.items():
        if key in parameters:
            accepted[key] = value
            continue
        for alias in aliases.get(key, ()):
            if alias in parameters:
                accepted[alias] = value
                break
    return function(**accepted)


def _split_module_values(values):
    modules = []
    for value in values or []:
        for item in str(value).split(","):
            name = item.strip()
            if name:
                modules.append(name)
    return modules


def _as_sequence(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [f"{key}={value[key]}" for key in sorted(value)]
    try:
        return list(value)
    except TypeError:
        return [value]


def _compact_text(value, limit=160):
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _result_mapping(result):
    if isinstance(result, dict):
        return dict(result)
    if dataclasses.is_dataclass(result):
        return dataclasses.asdict(result)
    if hasattr(result, "to_dict"):
        value = result.to_dict()
        if isinstance(value, dict):
            return dict(value)
    return {}


def _first_present(*mappings, keys):
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = mapping.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _memory_status(action, result, mapping, manifest):
    if result is True:
        return "ok"
    if result is False:
        return "failed"
    valid = _first_present(mapping, manifest, keys=("valid", "ok", "success"))
    if valid is False:
        return "failed"
    if valid is True:
        return "ok"
    status = _first_present(mapping, manifest, keys=("status", "result"))
    if status:
        return str(status)
    if action == "validate":
        return "ok"
    return "ok"


def _format_memory_summary(action, result):
    mapping = _result_mapping(result)
    manifest = mapping.get("manifest") if isinstance(mapping.get("manifest"), dict) else {}
    status = _memory_status(action, result, mapping, manifest)
    lines = [f"memory {action}: {status}"]

    if isinstance(result, Path):
        lines.append(f"path: {result}")
    elif isinstance(result, str):
        key = "path" if action in {"export", "import"} else "details"
        lines.append(f"{key}: {_compact_text(result)}")

    path = _first_present(
        mapping,
        manifest,
        keys=("pack_path", "output", "output_path", "path", "file"),
    )
    if path is not None and not isinstance(result, (str, Path)):
        lines.append(f"path: {path}")

    schema_version = _first_present(mapping, manifest, keys=("schema_version",))
    if schema_version:
        lines.append(f"schema: {schema_version}")

    preset = _first_present(mapping, manifest, keys=("preset",))
    if preset:
        lines.append(f"preset: {preset}")

    modules = _first_present(mapping, manifest, keys=("modules",))
    if modules:
        lines.append("modules: " + ", ".join(str(item) for item in _as_sequence(modules)))

    counts = _first_present(mapping, manifest, keys=("counts",))
    if isinstance(counts, dict) and counts:
        lines.append("counts: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))

    warnings = _as_sequence(_first_present(mapping, manifest, keys=("warnings",)))
    lines.append(f"warnings: {len(warnings)}")
    for warning in warnings:
        lines.append(f"warning: {_compact_text(warning)}")

    errors = _as_sequence(_first_present(mapping, manifest, keys=("errors",)))
    for error in errors:
        lines.append(f"error: {_compact_text(error)}")

    return lines


def _print_memory_summary(action, result):
    for line in _format_memory_summary(action, result):
        print(line)


def _format_retrieval_explanation(item):
    if not isinstance(item, dict):
        return f"- {_compact_text(item)}"
    score = item.get("score", "-")
    kind = str(item.get("kind", "episodic")).strip() or "episodic"
    source = str(item.get("source", "")).strip() or "-"
    text = _compact_text(item.get("text", ""))
    lines = [f"- score={score} kind={kind} source={source} text={text}"]
    score_breakdown = item.get("score_breakdown")
    if isinstance(score_breakdown, dict) and score_breakdown:
        parts = [f"{key}={score_breakdown[key]}" for key in sorted(score_breakdown)]
        lines.append(f"  score_breakdown: {', '.join(parts)}")
    return "\n".join(lines)


def _memory_explain_text(agent, query):
    if hasattr(agent, "memory_explain_text"):
        return str(agent.memory_explain_text(query))
    memory = getattr(agent, "memory", None)
    if memory is None or not hasattr(memory, "retrieval_explanations"):
        return "No memory explanation API is available."
    explanations = list(memory.retrieval_explanations(query))
    if not explanations:
        return "Memory explanation:\n- none"
    lines = ["Memory explanation:"]
    for item in explanations:
        lines.append(_format_retrieval_explanation(item))
    return "\n".join(lines)


def _memory_self_iteration_text(agent):
    if hasattr(agent, "memory_self_iteration_text"):
        return str(agent.memory_self_iteration_text())
    return "Memory self-iteration:\n- unavailable"


def _memory_self_iteration_notice(agent):
    if not hasattr(agent, "memory_self_iteration_status"):
        return ""
    status = agent.memory_self_iteration_status()
    queued = len(status.get("self_iteration_review_queued", []))
    compactions = len(status.get("episodic_compactions", []))
    rejections = len(status.get("self_iteration_rejections", []))
    if not queued and not compactions and not rejections:
        return ""
    parts = []
    if queued:
        noun = "candidate" if queued == 1 else "candidates"
        parts.append(f"queued {queued} durable memory {noun} for review")
    if compactions:
        parts.append(f"compacted {compactions} episodic note group")
    if rejections:
        parts.append(f"rejected {rejections} unsafe candidate")
    return "memory self-iteration: " + "; ".join(parts) + "; run /memory review to accept, edit, reject, or skip"


def _review_record_label(record):
    if not isinstance(record, dict):
        return _compact_text(record)
    topic = str(record.get("topic", "")).strip() or "-"
    text = _compact_text(record.get("text", ""))
    return f"{topic}: {text}"


def _prompt_review_topic(default_topic):
    topics = sorted(memorylib.DURABLE_TOPIC_DEFAULTS)
    while True:
        topic = input(f"topic [{default_topic}] ({', '.join(topics)}): ").strip() or default_topic
        if topic in memorylib.DURABLE_TOPIC_DEFAULTS:
            return topic
        print(f"invalid topic: {topic}")


def _print_review_apply_result(result, fallback_record):
    result = result if isinstance(result, dict) else {}
    status = str(result.get("status", "")).strip()
    record = result.get("record") if isinstance(result.get("record"), dict) else fallback_record
    if status == "accepted":
        print(f"accepted: {_review_record_label(record)}")
        return True
    if status == "rejected" and result.get("reason"):
        print(f"review action rejected: {result['reason']}")
        return False
    if status == "rejected":
        print(f"rejected: {_review_record_label(record)}")
        return True
    if status == "not_found":
        print(f"not found: {_review_record_label(fallback_record)}")
        return True
    print(f"memory review: unexpected status {status or '-'}")
    return False


def run_memory_review(agent):
    if not hasattr(agent, "memory_review_pending"):
        print("memory review: unavailable")
        return
    pending = list(agent.memory_review_pending())
    if not pending:
        print("memory review: no pending durable memory candidates")
        return

    print(f"memory review: {len(pending)} pending durable memory candidates")
    for index, record in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {_review_record_label(record)}")
        while True:
            action = input("accept/edit/reject/skip/quit> ").strip().lower()
            if action in {"accept", "a"}:
                result = agent.memory_review_accept(record.get("id", ""))
                if _print_review_apply_result(result, record):
                    break
                continue
            if action in {"edit", "e"}:
                topic = _prompt_review_topic(str(record.get("topic", "")).strip())
                text = input("text: ").strip() or str(record.get("text", "")).strip()
                result = agent.memory_review_edit(record.get("id", ""), topic=topic, text=text)
                if _print_review_apply_result(result, record):
                    break
                continue
            if action in {"reject", "r"}:
                result = agent.memory_review_reject(record.get("id", ""))
                print(f"rejected: {_review_record_label(result.get('record', record))}")
                break
            if action in {"skip", "s"}:
                print(f"skipped: {_review_record_label(record)}")
                break
            if action in {"quit", "q", "exit"}:
                return
            print("usage: accept, edit, reject, skip, or quit")


def _resolve_export_modules(api, preset, requested_modules):
    if hasattr(api, "resolve_modules"):
        resolved = _call_memory_pack_function(
            api.resolve_modules,
            preset=preset,
            modules=requested_modules or None,
        )
        return _as_sequence(resolved)

    if requested_modules:
        return list(requested_modules)

    preset_modules = getattr(api, "PRESET_MODULES", {})
    if preset and isinstance(preset_modules, dict):
        return _as_sequence(preset_modules.get(preset, ()))
    return []


def _run_memory_export(cwd, preset=None, module_values=None, output=None):
    api = _load_memory_pack_api()
    requested_modules = _split_module_values(module_values)
    if not preset and not requested_modules:
        preset = "safe-transfer"
    modules = _resolve_export_modules(api, preset, requested_modules)
    explicit_modules = modules if requested_modules else None
    result = _call_memory_pack_function(
        api.export_memory_pack,
        aliases={
            "cwd": ("workspace_root", "repo_root"),
            "output": ("output_path",),
            "modules": ("module_names",),
        },
        cwd=cwd,
        preset=preset,
        modules=explicit_modules,
        output=output,
    )
    _print_memory_summary("export", result)
    return result


def _prompt_custom_modules():
    api = _load_memory_pack_api()
    modules = _as_sequence(getattr(api, "MODULES", getattr(api, "MEMORY_PACK_MODULES", ())))
    selected = []
    if not modules:
        return selected
    print("Memory export modules:")
    for module in modules:
        answer = _menu_input(f"Include {module}? [y/N] ")
        if answer is None:
            return []
        if answer.lower() in {"y", "yes"}:
            selected.append(str(module))
    return selected


def _run_memory_import(pack_path, cwd):
    api = _load_memory_pack_api()
    pack_path = _resolve_pack_path_for_cwd(pack_path, cwd)
    result = _call_memory_pack_function(
        api.import_memory_pack,
        aliases={
            "pack_path": ("path", "pack"),
            "cwd": ("workspace_root", "repo_root"),
        },
        pack_path=pack_path,
        cwd=cwd,
    )
    _print_memory_summary("import", result)
    return result


def _run_memory_inspect(pack_path, cwd):
    api = _load_memory_pack_api()
    pack_path = _resolve_pack_path_for_cwd(pack_path, cwd)
    result = _call_memory_pack_function(
        api.inspect_memory_pack,
        aliases={
            "pack_path": ("path", "pack"),
            "cwd": ("workspace_root", "repo_root"),
        },
        pack_path=pack_path,
        cwd=cwd,
    )
    _print_memory_summary("inspect", result)
    return result


def _run_memory_validate(pack_path, cwd):
    api = _load_memory_pack_api()
    pack_path = _resolve_pack_path_for_cwd(pack_path, cwd)
    result = _call_memory_pack_function(
        api.validate_memory_pack,
        aliases={
            "pack_path": ("path", "pack"),
            "cwd": ("workspace_root", "repo_root"),
        },
        pack_path=pack_path,
        cwd=cwd,
    )
    _print_memory_summary("validate", result)
    return result


def _resolve_pack_path_for_cwd(pack_path, cwd):
    path = Path(pack_path)
    if path.is_absolute():
        return path
    return Path(cwd).resolve() / path


def _memory_result_failed(action, result):
    mapping = _result_mapping(result)
    manifest = mapping.get("manifest") if isinstance(mapping.get("manifest"), dict) else {}
    return _memory_status(action, result, mapping, manifest) == "failed"


def build_memory_arg_parser():
    parser = argparse.ArgumentParser(
        prog="repo-harness memory",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Export, import, inspect, or validate RepoHarness memory packs.",
    )
    subparsers = parser.add_subparsers(dest="command")

    export_parser = subparsers.add_parser("export", help="Export a memory pack.")
    export_parser.add_argument("--preset", default=None, help="Export preset, for example safe-transfer, continue-work, or full-recovery.")
    export_parser.add_argument("--modules", action="append", default=[], help="Comma-separated module names. Can be repeated.")
    export_parser.add_argument("--custom", action="store_true", help="Interactively choose memory modules.")
    export_parser.add_argument("--output", default=None, help="Output pack path. Defaults to the memory pack API's generated path.")
    export_parser.add_argument("--cwd", default=".", help="Workspace directory.")

    import_parser = subparsers.add_parser("import", help="Import a memory pack.")
    import_parser.add_argument("pack_path", help="Path to the memory pack.")
    import_parser.add_argument("--cwd", default=".", help="Workspace directory.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a memory pack.")
    inspect_parser.add_argument("pack_path", help="Path to the memory pack.")
    inspect_parser.add_argument("--cwd", default=".", help="Workspace directory.")

    validate_parser = subparsers.add_parser("validate", help="Validate a memory pack.")
    validate_parser.add_argument("pack_path", help="Path to the memory pack.")
    validate_parser.add_argument("--cwd", default=".", help="Workspace directory.")
    return parser


def handle_memory_command(argv):
    parser = build_memory_arg_parser()
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)

    try:
        if args.command == "export":
            module_values = list(args.modules)
            preset = args.preset
            if args.custom:
                if args.preset:
                    print("--custom cannot be combined with --preset", file=sys.stderr)
                    return 1
                if not module_values:
                    module_values = _prompt_custom_modules()
                if not module_values:
                    print("memory export: no modules selected", file=sys.stderr)
                    return 1
                preset = None
            result = _run_memory_export(
                cwd=args.cwd,
                preset=preset,
                module_values=module_values,
                output=args.output,
            )
            return 1 if _memory_result_failed("export", result) else 0
        if args.command == "import":
            result = _run_memory_import(args.pack_path, cwd=args.cwd)
            return 1 if _memory_result_failed("import", result) else 0
        if args.command == "inspect":
            result = _run_memory_inspect(args.pack_path, cwd=args.cwd)
            return 1 if _memory_result_failed("inspect", result) else 0
        if args.command == "validate":
            result = _run_memory_validate(args.pack_path, cwd=args.cwd)
            return 1 if _memory_result_failed("validate", result) else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 0


def _menu_input(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("")
        return None


def _menu_output_path():
    value = _menu_input("Output path (blank for default): ")
    if value is None:
        return None, False
    return value or None, True


def _run_memory_menu_export(cwd, preset):
    output, ok = _menu_output_path()
    if not ok:
        print("memory pack: cancelled")
        return
    _run_memory_export(cwd=cwd, preset=preset, output=output)


def run_memory_pack_menu(cwd):
    menu = textwrap.dedent(
        """\
        Memory pack

        1. Safe transfer export
           Export stable project memory for another computer.

        2. Continue work export
           Export stable memory plus current task context and recent file summaries.

        3. Full recovery export
           Export stable memory, working context, sessions, checkpoints, and run artifacts.
           Privacy warning: may include prompts, tool outputs, local paths, reports, and traces.

        4. Import pack
           Merge a memory pack into this workspace without overwriting existing memory.

        5. Inspect/validate pack
           Preview and validate a pack before importing it.

        0. Cancel

        Advanced: repo-harness memory export/import/inspect/validate
        """
    ).strip()

    while True:
        print(menu)
        choice = _menu_input("Choose an option: ")
        if choice is None or choice in {"0", "q", "quit", "cancel"}:
            print("memory pack: cancelled")
            return

        try:
            if choice == "1":
                _run_memory_menu_export(cwd, "safe-transfer")
                return
            if choice == "2":
                _run_memory_menu_export(cwd, "continue-work")
                return
            if choice == "3":
                print(
                    "Privacy warning: full recovery packs may include prompts, tool outputs, "
                    "local paths, reports, traces, sessions, and checkpoints."
                )
                confirm = _menu_input("Type FULL RECOVERY to continue: ")
                if confirm != "FULL RECOVERY":
                    print("memory pack: cancelled")
                    return
                _run_memory_menu_export(cwd, "full-recovery")
                return
            if choice == "4":
                pack_path = _menu_input("Pack path: ")
                if not pack_path:
                    print("memory pack: cancelled")
                    return
                _run_memory_import(pack_path, cwd=cwd)
                return
            if choice == "5":
                pack_path = _menu_input("Pack path: ")
                if not pack_path:
                    print("memory pack: cancelled")
                    return
                _run_memory_inspect(pack_path, cwd=cwd)
                _run_memory_validate(pack_path, cwd=cwd)
                return
        except Exception as exc:
            print(f"memory pack error: {exc}", file=sys.stderr)
            return

        print("Choose 1, 2, 3, 4, 5, or 0.")


def _build_model_client(args):
    provider = getattr(args, "provider", "openai")
    # CLI 只负责把 provider 选择翻译成具体 client。
    # 真正的提示词格式、缓存支持、HTTP 协议差异，都封装在 models.py 里。
    if provider == "openai":
        model = _effective_model(args, provider)
        base_url = getattr(args, "base_url", None) or os.environ.get("OPENAI_API_BASE") or DEFAULT_OPENAI_BASE_URL
        api_key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAICompatibleModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", getattr(args, "ollama_timeout", 300)),
        )
    if provider == "anthropic":
        model = _effective_model(args, provider)
        base_url = getattr(args, "base_url", None) or os.environ.get("ANTHROPIC_API_BASE") or DEFAULT_ANTHROPIC_BASE_URL
        api_key = _first_env("ANTHROPIC_API_KEY", "RIGHT_CODES_API_KEY", "OPENAI_API_KEY")
        return AnthropicCompatibleModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", getattr(args, "ollama_timeout", 300)),
        )

    model = _effective_model(args, provider)
    host = getattr(args, "host", DEFAULT_OLLAMA_HOST)
    return OllamaModelClient(
        model=model,
        host=host,
        temperature=args.temperature,
        top_p=args.top_p,
        timeout=args.ollama_timeout,
    )


def build_welcome(agent, model, host):
    width = max(68, min(shutil.get_terminal_size((80, 20)).columns, 84))
    inner = width - 4
    gap = 3
    left_width = (inner - gap) // 2
    right_width = inner - gap - left_width

    def row(text):
        body = middle(text, width - 4)
        return f"| {body.ljust(width - 4)} |"

    def divider(char="-"):
        return "+" + char * (width - 2) + "+"

    def center(text):
        body = middle(text, inner)
        return f"| {body.center(inner)} |"

    def cell(label, value, size):
        body = middle(f"{label:<9} {value}", size)
        return body.ljust(size)

    def pair(left_label, left_value, right_label, right_value):
        left = cell(left_label, left_value, left_width)
        right = cell(right_label, right_value, right_width)
        return f"| {left}{' ' * gap}{right} |"

    line = divider("=")
    rows = [center(text) for text in WELCOME_ART]
    rows.extend(
        [
            center(WELCOME_NAME),
            center(WELCOME_SUBTITLE),
            center(WELCOME_STATUS),
            divider("-"),
            row(""),
            row("WORKSPACE  " + middle(agent.workspace.cwd, inner - 11)),
            pair("MODEL", model, "BRANCH", agent.workspace.branch),
            pair("APPROVAL", agent.approval_policy, "SESSION", agent.session["id"]),
            row(""),
        ]
    )
    return "\n".join([line, *rows, line])


def build_agent(args):
    """根据 CLI 参数装配出一个可运行的 RepoHarness 实例。

    为什么存在：
    命令行参数只是字符串和开关，runtime 需要的是已经装配好的对象图：
    model client、workspace snapshot、session store、secret 配置等。
    这个函数负责把“启动参数”翻译成“agent 运行现场”。

    输入 / 输出：
    - 输入：`argparse` 解析后的 `args`
    - 输出：一个新的 `RepoHarness`，或一个从旧 session 恢复出来的 `RepoHarness`

    在 agent 链路里的位置：
    它是整个程序启动链路里最靠近 runtime 的装配点。`main()` 先调它，
    得到 agent 后，后面无论是 one-shot 还是 REPL 模式，都会落到 `ask()`。
    """
    # 这里是 CLI 到 runtime 的装配点：
    # 先整理 secret 名单，再采集工作区快照，随后决定是恢复旧 session
    # 还是创建一个新的 RepoHarness 实例。
    configured_secret_names = _configured_secret_names(args)
    workspace = WorkspaceContext.build(args.cwd)
    store = SessionStore(workspace.repo_root + "/.repo-harness/sessions")
    model = _build_model_client(args)
    session_id = args.resume
    if session_id == "latest":
        session_id = store.latest()
    if session_id:
        return RepoHarness.from_session(
            model_client=model,
            workspace=workspace,
            session_store=store,
            session_id=session_id,
            approval_policy=args.approval,
            max_steps=args.max_steps,
            max_new_tokens=args.max_new_tokens,
            secret_env_names=configured_secret_names,
        )
    return RepoHarness(
        model_client=model,
        workspace=workspace,
        session_store=store,
        approval_policy=args.approval,
        max_steps=args.max_steps,
        max_new_tokens=args.max_new_tokens,
        secret_env_names=configured_secret_names,
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Minimal coding agent for Ollama, OpenAI-compatible, or Anthropic-compatible models.",
        epilog="Advanced memory packs: repo-harness memory export/import/inspect/validate",
    )
    parser.add_argument("prompt", nargs="*", help="Optional one-shot prompt.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument("--provider", choices=("ollama", "openai", "anthropic"), default="openai", help="Model backend to use.")
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override. Defaults to qwen3.5:4b for Ollama, OPENAI_MODEL for openai, and ANTHROPIC_MODEL for anthropic when set.",
    )
    parser.add_argument("--host", default=DEFAULT_OLLAMA_HOST, help="Ollama server URL.")
    parser.add_argument("--base-url", default=None, help="Provider API base URL for openai or anthropic.")
    parser.add_argument("--ollama-timeout", type=int, default=300, help="Ollama request timeout in seconds.")
    parser.add_argument("--openai-timeout", type=int, default=300, help="OpenAI-compatible request timeout in seconds.")
    parser.add_argument("--resume", default=None, help="Session id to resume or 'latest'.")
    parser.add_argument("--approval", choices=("ask", "auto", "never"), default="ask", help="Approval policy for risky tools.")
    parser.add_argument(
        "--secret-env-name",
        dest="secret_env_names",
        action="append",
        default=[],
        help="Extra environment variable names to treat as secrets for trace/report redaction.",
    )
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum tool/model iterations per request.")
    parser.add_argument("--max-new-tokens", type=int, default=512, help="Maximum model output tokens per step.")
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature sent to Ollama.")
    parser.add_argument("--top-p", type=float, default=0.9, help="Top-p sampling value sent to Ollama.")
    return parser


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "memory":
        return handle_memory_command(raw_argv[1:])

    args = build_arg_parser().parse_args(raw_argv)
    agent = build_agent(args)

    model = getattr(agent.model_client, "model", getattr(args, "model", DEFAULT_OLLAMA_MODEL))
    host = getattr(agent.model_client, "host", getattr(agent.model_client, "base_url", getattr(args, "host", DEFAULT_OLLAMA_HOST)))
    print(build_welcome(agent, model=model, host=host))

    if args.prompt:
        # one-shot 模式：只跑一次 ask，不进入 REPL 循环。
        prompt = " ".join(args.prompt).strip()
        if prompt:
            print()
            try:
                print(agent.ask(prompt))
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        return 0

    while True:
        # 交互模式：每次读取一条用户输入，交给同一个 agent，
        # 因此 session history 和 working memory 会跨轮延续。
        try:
            user_input = input("\nrepo-harness> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not user_input:
            continue
        if user_input in {"/exit", "/quit"}:
            return 0
        if user_input == "/help":
            print(HELP_DETAILS)
            continue
        if user_input in {"/memory_pack", "/memory-pack"}:
            run_memory_pack_menu(agent.workspace.cwd)
            continue
        if user_input == "/memory review":
            run_memory_review(agent)
            continue
        if user_input == "/memory self_iteration":
            print(_memory_self_iteration_text(agent))
            continue
        if user_input == "/memory":
            print(agent.memory_text())
            continue
        if user_input.startswith("/memory_explain"):
            query = user_input[len("/memory_explain"):].strip()
            if not query:
                print("usage: /memory_explain <query>")
                continue
            print(_memory_explain_text(agent, query))
            continue
        if user_input == "/session":
            print(agent.session_path)
            continue
        if user_input == "/reset":
            agent.reset()
            print("session reset")
            continue

        print()
        try:
            print(agent.ask(user_input))
            notice = _memory_self_iteration_notice(agent)
            if notice:
                print(notice)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)


