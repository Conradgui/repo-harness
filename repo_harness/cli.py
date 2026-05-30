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
from .config import (
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    resolve_runtime_config,
)
from .models import AnthropicCompatibleModelClient, ChatCompletionsCompatibleModelClient, OllamaModelClient, OpenAICompatibleModelClient
from .models import _sanitize_base_url
from .provider_registry import provider_choices
from .runtime import RepoHarness
from .session_store import SessionStore
from .workspace import WorkspaceContext, middle

DEFAULT_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "CHAT_COMPLETIONS_API_KEY",
    "OPENAI_API_TOKEN",
    "REPO_HARNESS_API_KEY",
    "REPO_HARNESS_OPENAI_API_KEY",
    "REPO_HARNESS_CHAT_COMPLETIONS_API_KEY",
    "REPO_HARNESS_ANTHROPIC_API_KEY",
    "REPO_HARNESS_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
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
    /memory organize  Organize memory candidates into the Review Queue.
    /memory self_iteration  Show the latest memory self-iteration status.
    /memory_explain <query>  Explain which memory notes match a query.
    /remember <text>  Queue a durable memory candidate for /memory review.
    /skills  List available skills.
    /skill <name> [args] Run a skill.
    /auto-issue-fix [args] Run or preview Auto Issue Fix; no args starts guided mode in REPL.
    /agents  Show subagent worker status.
    /subagent explore <task>  Run a read-only worker.
    /subagent worker --scope <path[,path]> <task>  Run a scoped write worker.
    /plan <topic>  Enter plan mode and write .repo-harness/plans/<topic>-plan.md.
    /plan-exit  Leave plan mode.
    /mode  Show the current runtime mode.
    /usage  Show provider and latest usage metadata.
    /model [name]  Show or change the current runtime model only.
    /history  Show compact session history.
    /context  Show context usage estimates.
    /compact  Manually compact session history.
    /working-memory  Show working memory.
    /memory_pack  Export, import, inspect, or validate memory packs.
    /session Show the path to the saved session file.
    /reset   Clear the current session history and memory.
    /exit    Exit the agent.
    """
).strip()


SECRET_ENV_NAMES_VAR = "REPO_HARNESS_SECRET_ENV_NAMES"


class _ExplicitStoreAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        del parser, option_string
        setattr(namespace, self.dest, values)
        setattr(namespace, f"_{self.dest}_explicit", True)


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
    if provider == "chat-completions":
        model = os.environ.get("CHAT_COMPLETIONS_MODEL") or os.environ.get("REPO_HARNESS_MODEL")
        if model:
            return model
        return DEFAULT_OPENAI_MODEL
    if provider == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL")
        if model:
            return model
        return DEFAULT_ANTHROPIC_MODEL
    if provider == "deepseek":
        model = os.environ.get("DEEPSEEK_MODEL") or os.environ.get("REPO_HARNESS_MODEL")
        if model:
            return model
        return "deepseek-v4-pro"
    return DEFAULT_OLLAMA_MODEL


def _first_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _first_env_from(environment, *names):
    environment = environment or os.environ
    for name in names:
        value = environment.get(name)
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


def _prompt_review_topic(default_topic, display=None):
    topics = sorted(memorylib.DURABLE_TOPIC_DEFAULTS)
    if display:
        display.show_info(f"Available topics: {', '.join(topics)}")
        topic = display.prompt_text(f"topic [{default_topic}]")
    else:
        topic = input(f"topic [{default_topic}] ({', '.join(topics)}): ").strip()
    topic = topic.strip() or default_topic
    if topic not in memorylib.DURABLE_TOPIC_DEFAULTS:
        if display:
            display.show_warning(f"invalid topic: {topic}, using default: {default_topic}")
        else:
            print(f"invalid topic: {topic}")
        return default_topic
    return topic


def _print_review_apply_result(result, fallback_record, display=None):
    result = result if isinstance(result, dict) else {}
    status = str(result.get("status", "")).strip()
    record = result.get("record") if isinstance(result.get("record"), dict) else fallback_record
    label = _review_record_label(record)
    if status == "accepted":
        if display:
            display.show_success(f"accepted: {label}")
        else:
            print(f"accepted: {label}")
        return True
    if status == "rejected" and result.get("reason"):
        if display:
            display.show_warning(f"review action rejected: {result['reason']}")
        else:
            print(f"review action rejected: {result['reason']}")
        return False
    if status == "rejected":
        if display:
            display.show_warning(f"rejected: {label}")
        else:
            print(f"rejected: {label}")
        return True
    if status == "not_found":
        if display:
            display.show_warning(f"not found: {_review_record_label(fallback_record)}")
        else:
            print(f"not found: {_review_record_label(fallback_record)}")
        return True
    if display:
        display.show_warning(f"memory review: unexpected status {status or '-'}")
    else:
        print(f"memory review: unexpected status {status or '-'}")
    return False


def run_memory_review(agent, display=None):
    if not hasattr(agent, "memory_review_pending"):
        if display:
            display.show_warning("memory review: unavailable")
        else:
            print("memory review: unavailable")
        return
    pending = list(agent.memory_review_pending())
    if not pending:
        if display:
            display.show_info("memory review: no pending durable memory candidates")
        else:
            print("memory review: no pending durable memory candidates")
        return

    if display:
        display.show_info(f"memory review: {len(pending)} pending durable memory candidates")
    else:
        print(f"memory review: {len(pending)} pending durable memory candidates")

    for index, record in enumerate(pending, start=1):
        label = _review_record_label(record)
        if display:
            display.show_info(f"[{index}/{len(pending)}] {label}")
        else:
            print(f"[{index}/{len(pending)}] {label}")

        while True:
            if display:
                action = display.prompt_choice(
                    "accept/edit/reject/skip/quit",
                    ["accept", "edit", "reject", "skip", "quit"],
                )
            else:
                action = input("accept/edit/reject/skip/quit> ").strip().lower()

            if action in {"accept", "a"}:
                result = agent.memory_review_accept(record.get("id", ""))
                if _print_review_apply_result(result, record, display):
                    break
                continue
            if action in {"edit", "e"}:
                topic = _prompt_review_topic(str(record.get("topic", "")).strip(), display)
                if display:
                    text = display.prompt_text("text") or str(record.get("text", "")).strip()
                else:
                    text = input("text: ").strip() or str(record.get("text", "")).strip()
                result = agent.memory_review_edit(record.get("id", ""), topic=topic, text=text)
                if _print_review_apply_result(result, record, display):
                    break
                continue
            if action in {"reject", "r"}:
                result = agent.memory_review_reject(record.get("id", ""))
                rej_label = _review_record_label(result.get("record", record))
                if display:
                    display.show_warning(f"rejected: {rej_label}")
                else:
                    print(f"rejected: {rej_label}")
                break
            if action in {"skip", "s"}:
                if display:
                    display.show_info(f"skipped: {label}")
                else:
                    print(f"skipped: {label}")
                break
            if action in {"quit", "q", "exit"}:
                return
            if display:
                display.show_warning("usage: accept, edit, reject, skip, or quit")
            else:
                print("usage: accept, edit, reject, skip, or quit")


def run_remember(agent, text, display=None):
    if not hasattr(agent, "remember_candidate"):
        if display:
            display.show_warning("remember: unavailable")
        else:
            print("remember: unavailable")
        return
    result = agent.remember_candidate(text)
    status = result.get("status")
    if status == "usage":
        if display:
            display.show_warning("usage: /remember <text>")
        else:
            print("usage: /remember <text>")
        return
    if status == "rejected":
        if display:
            display.show_warning(f"remember rejected: {result.get('reason', 'unknown')}")
        else:
            print(f"remember rejected: {result.get('reason', 'unknown')}")
        return
    if status == "duplicate":
        if display:
            display.show_info("remember: candidate already pending; run /memory review")
        else:
            print("remember: candidate already pending; run /memory review")
        return
    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    label = _review_record_label(record)
    if display:
        display.show_success(f"remember: queued durable memory candidate for review: {label}")
        display.show_info("run /memory review to accept, edit, reject, or skip")
    else:
        print(f"remember: queued durable memory candidate for review: {label}")
        print("run /memory review to accept, edit, reject, or skip")


def run_subagent(agent, text, display=None):
    parts = text.split()
    usage = "usage: /subagent explore <task> or /subagent worker --scope <path[,path]> <task>"
    if not parts or parts[0] not in {"explore", "worker"}:
        if display:
            display.show_warning(usage)
        else:
            print(usage)
        return
    mode = parts.pop(0)
    write_scope = []
    if mode == "worker":
        if len(parts) < 3 or parts[0] != "--scope":
            if display:
                display.show_warning("usage: /subagent worker --scope <path[,path]> <task>")
            else:
                print("usage: /subagent worker --scope <path[,path]> <task>")
            return
        write_scope = [item.strip() for item in parts[1].split(",") if item.strip()]
        parts = parts[2:]
    task = " ".join(parts).strip()
    if not task:
        if display:
            display.show_warning(usage)
        else:
            print(usage)
        return
    result = agent.spawn_worker(task, task, subagent_type="Explore" if mode == "explore" else "worker", write_scope=write_scope)
    if display:
        display.show_info(f"{result['id']} {result['status']}: {result.get('result', '')}")
    else:
        print(f"{result['id']} {result['status']}: {result.get('result', '')}")


def _format_usage(agent):
    metadata = dict(getattr(agent, "last_completion_metadata", {}) or {})
    model = str(getattr(agent.model_client, "model", metadata.get("provider_model", "")) or "-")
    base_url = metadata.get("provider_base_url") or getattr(agent.model_client, "base_url", getattr(agent.model_client, "host", ""))
    if base_url:
        base_url = _sanitize_base_url(base_url)
    lines = [
        "Usage:",
        f"provider protocol: {metadata.get('provider_protocol', agent.model_client.__class__.__name__)}",
        f"model: {model}",
        f"base URL: {base_url or '-'}",
        f"provider attempts: {metadata.get('provider_attempts', 0)}",
        f"provider retry count: {metadata.get('provider_retry_count', 0)}",
    ]
    for key in ("input_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens"):
        if key in metadata:
            lines.append(f"{key}: {metadata[key]}")
    return "\n".join(lines)


def _format_context(agent):
    usage = agent.context_usage()
    lines = ["context_usage:"]
    lines.append(f"total_estimated_tokens: {usage.get('total_estimated_tokens', 0)}")
    for name, section in usage.get("sections", {}).items():
        lines.append(f"- {name}: chars={section.get('chars', 0)} tokens={section.get('tokens', 0)}")
    return "\n".join(lines)


def _format_history(agent):
    return f"History for session {agent.session['id']}:\n{agent.history_text()}"


def _format_compaction(summary):
    return "\n".join(
        [
            "compact:",
            f"pre_tokens: {summary.get('pre_tokens', 0)}",
            f"post_tokens: {summary.get('post_tokens', 0)}",
            f"trigger: {summary.get('trigger', '')}",
        ]
    )


def handle_repl_command(agent, user_input, *, interactive=False, input_func=input):
    user_input = str(user_input or "").strip()
    if not user_input.startswith("/"):
        return False, False, ""
    if user_input in {"/exit", "/quit"}:
        return True, True, ""
    if user_input == "/help":
        return True, False, HELP_DETAILS
    if user_input == "/skills":
        return True, False, agent.render_skills()
    if user_input.startswith("/skill"):
        body = user_input[len("/skill"):].strip()
        if not body:
            return True, False, "usage: /skill <name> [args]"
        name, _, arguments = body.partition(" ")
        return True, False, agent.invoke_skill(name, arguments)
    if user_input.startswith("/auto-issue-fix"):
        from .auto_issue_fix import handle_auto_issue_fix_repl_command

        body = user_input[len("/auto-issue-fix"):].strip()
        _code, output = handle_auto_issue_fix_repl_command(
            body,
            workspace_root=getattr(agent, "cwd", "."),
            interactive=interactive,
            input_func=input_func,
        )
        return True, False, output
    if user_input == "/agents":
        return True, False, agent.render_workers()
    if user_input.startswith("/subagent"):
        return False, False, ""
    if user_input == "/plan-exit":
        agent.exit_plan_mode()
        return True, False, "runtime mode: default"
    if user_input.startswith("/plan"):
        body = user_input[len("/plan"):].strip()
        if agent.runtime_mode == "plan":
            return True, False, f"plan mode already active: {agent.active_plan_path}"
        if not body:
            return True, False, "usage: /plan <topic>"
        topic = body.split()[0]
        plan_path = agent.enter_plan_mode(topic)
        return True, False, f"runtime mode: plan\nplan path: {plan_path}"
    if user_input == "/mode":
        output = f"runtime mode: {agent.runtime_mode}"
        if agent.active_plan_path:
            output += f"\nplan path: {agent.active_plan_path}"
        return True, False, output
    if user_input.startswith("/model"):
        body = user_input[len("/model"):].strip()
        if not body:
            return True, False, f"model: {getattr(agent.model_client, 'model', '-')}"
        if hasattr(agent.model_client, "model"):
            agent.model_client.model = body
        return True, False, f"model: {body}"
    if user_input == "/usage":
        return True, False, _format_usage(agent)
    if user_input == "/history":
        return True, False, _format_history(agent)
    if user_input == "/context":
        return True, False, _format_context(agent)
    if user_input == "/working-memory":
        return True, False, "Working memory:\n" + agent.memory_text()
    if user_input == "/compact":
        return True, False, _format_compaction(agent.compact_history(trigger="manual"))
    if user_input == "/memory":
        return True, False, agent.memory_text()
    if user_input == "/memory organize":
        return True, False, agent.memory_organize_text()
    if user_input == "/memory self_iteration":
        return True, False, _memory_self_iteration_text(agent)
    if user_input.startswith("/memory_explain"):
        query = user_input[len("/memory_explain"):].strip()
        if not query:
            return True, False, "usage: /memory_explain <query>"
        return True, False, _memory_explain_text(agent, query)
    if user_input.startswith("/remember"):
        return False, False, ""
    if user_input in {"/memory review", "/memory_pack", "/memory-pack"}:
        return False, False, ""
    if user_input == "/session":
        return True, False, str(agent.session_path)
    if user_input == "/reset":
        agent.reset()
        return True, False, "session reset"
    return False, False, ""


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


def _menu_input(prompt, display=None):
    if display:
        return display.prompt_text(prompt)
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("")
        return None


def _menu_output_path(display=None):
    value = _menu_input("Output path (blank for default): ", display)
    if value is None:
        return None, False
    return value or None, True


def _run_memory_menu_export(cwd, preset, display=None):
    output, ok = _menu_output_path(display)
    if not ok:
        if display:
            display.show_info("memory pack: cancelled")
        else:
            print("memory pack: cancelled")
        return
    _run_memory_export(cwd=cwd, preset=preset, output=output)


def run_memory_pack_menu(cwd, display=None):
    menu_options = [
        ("safe-transfer", "Export stable project memory for another computer"),
        ("continue-work", "Export stable memory plus current task context and recent file summaries"),
        ("full-recovery", "Export everything (privacy warning: includes prompts, traces, paths)"),
        ("import", "Merge a memory pack into this workspace"),
        ("inspect", "Preview and validate a pack before importing"),
    ]

    while True:
        if display:
            display.show_menu("Memory Pack", menu_options)
            choice = display.prompt_choice("Choose an option", ["1", "2", "3", "4", "5", "0"])
        else:
            print(textwrap.dedent("""\
                Memory pack
                1. Safe transfer export
                2. Continue work export
                3. Full recovery export (privacy warning)
                4. Import pack
                5. Inspect/validate pack
                0. Cancel
            """))
            choice = _menu_input("Choose an option: ")

        if choice is None or choice in {"0", "q", "quit", "cancel"}:
            if display:
                display.show_info("memory pack: cancelled")
            else:
                print("memory pack: cancelled")
            return

        try:
            if choice == "1":
                _run_memory_menu_export(cwd, "safe-transfer", display)
                return
            if choice == "2":
                _run_memory_menu_export(cwd, "continue-work", display)
                return
            if choice == "3":
                if display:
                    display.show_warning(
                        "Full recovery packs may include prompts, tool outputs, "
                        "local paths, reports, traces, sessions, and checkpoints."
                    )
                    confirm = display.prompt_text("Type FULL RECOVERY to continue")
                else:
                    print(
                        "Privacy warning: full recovery packs may include prompts, tool outputs, "
                        "local paths, reports, traces, sessions, and checkpoints."
                    )
                    confirm = _menu_input("Type FULL RECOVERY to continue: ")
                if confirm != "FULL RECOVERY":
                    if display:
                        display.show_info("memory pack: cancelled")
                    else:
                        print("memory pack: cancelled")
                    return
                _run_memory_menu_export(cwd, "full-recovery", display)
                return
            if choice == "4":
                pack_path = _menu_input("Pack path: ", display)
                if not pack_path:
                    if display:
                        display.show_info("memory pack: cancelled")
                    else:
                        print("memory pack: cancelled")
                    return
                _run_memory_import(pack_path, cwd=cwd)
                return
            if choice == "5":
                pack_path = _menu_input("Pack path: ", display)
                if not pack_path:
                    if display:
                        display.show_info("memory pack: cancelled")
                    else:
                        print("memory pack: cancelled")
                    return
                _run_memory_inspect(pack_path, cwd=cwd)
                _run_memory_validate(pack_path, cwd=cwd)
                return
        except Exception as exc:
            if display:
                display.show_error(f"memory pack error: {exc}")
            else:
                print(f"memory pack error: {exc}", file=sys.stderr)
            return

        if display:
            display.show_warning("Choose 1, 2, 3, 4, 5, or 0.")
        else:
            print("Choose 1, 2, 3, 4, 5, or 0.")


def _build_model_client(args, runtime_config=None):
    provider = runtime_config.provider if runtime_config is not None else getattr(args, "provider", "openai")
    profile = runtime_config.provider_profile if runtime_config is not None else None
    environment = getattr(runtime_config, "environment", os.environ) if runtime_config is not None else os.environ
    # CLI 只负责把 provider 选择翻译成具体 client。
    # 真正的提示词格式、缓存支持、HTTP 协议差异，都封装在 models.py 里。
    if provider == "openai":
        model = profile.model if profile is not None else _effective_model(args, provider)
        base_url = profile.base_url if profile is not None else (
            getattr(args, "base_url", None) or os.environ.get("OPENAI_API_BASE") or DEFAULT_OPENAI_BASE_URL
        )
        api_key_env = profile.api_key_env if profile is not None else "OPENAI_API_KEY"
        api_key = _first_env_from(
            environment,
            api_key_env,
            "REPO_HARNESS_OPENAI_API_KEY",
            "REPO_HARNESS_API_KEY",
            "OPENAI_API_KEY",
        )
        return OpenAICompatibleModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", getattr(args, "ollama_timeout", 300)),
        )
    if provider == "chat-completions":
        model = profile.model if profile is not None else _effective_model(args, provider)
        base_url = profile.base_url if profile is not None else (
            getattr(args, "base_url", None) or os.environ.get("CHAT_COMPLETIONS_API_BASE") or DEFAULT_OPENAI_BASE_URL
        )
        api_key_env = profile.api_key_env if profile is not None else "CHAT_COMPLETIONS_API_KEY"
        api_key = _first_env_from(
            environment,
            api_key_env,
            "REPO_HARNESS_CHAT_COMPLETIONS_API_KEY",
            "REPO_HARNESS_API_KEY",
            "CHAT_COMPLETIONS_API_KEY",
            "OPENAI_API_KEY",
        )
        return ChatCompletionsCompatibleModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", getattr(args, "ollama_timeout", 300)),
        )
    if provider in {"anthropic", "deepseek"}:
        model = profile.model if profile is not None else _effective_model(args, provider)
        base_url = profile.base_url if profile is not None else (
            getattr(args, "base_url", None) or os.environ.get("ANTHROPIC_API_BASE") or DEFAULT_ANTHROPIC_BASE_URL
        )
        api_key_env = profile.api_key_env if profile is not None else "ANTHROPIC_API_KEY"
        fallback_names = (
            api_key_env,
            "REPO_HARNESS_DEEPSEEK_API_KEY" if provider == "deepseek" else "REPO_HARNESS_ANTHROPIC_API_KEY",
            "REPO_HARNESS_API_KEY",
            "DEEPSEEK_API_KEY" if provider == "deepseek" else "ANTHROPIC_API_KEY",
            "RIGHT_CODES_API_KEY",
            "OPENAI_API_KEY",
        )
        api_key = _first_env_from(environment, *fallback_names)
        return AnthropicCompatibleModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=args.temperature,
            timeout=getattr(args, "openai_timeout", getattr(args, "ollama_timeout", 300)),
        )

    model = profile.model if profile is not None else _effective_model(args, provider)
    host = profile.base_url if profile is not None else getattr(args, "host", DEFAULT_OLLAMA_HOST)
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
    workspace = WorkspaceContext.build(args.cwd)
    runtime_config = resolve_runtime_config(args, workspace)
    configured_secret_names = _configured_secret_names(args)
    store = SessionStore(workspace.repo_root + "/.repo-harness/sessions")
    model = _build_model_client(args, runtime_config=runtime_config)
    approval = "auto" if getattr(args, "trust_session", False) else args.approval
    session_id = args.resume
    if session_id == "latest":
        session_id = store.latest()
    if session_id:
        return RepoHarness.from_session(
            model_client=model,
            workspace=workspace,
            session_store=store,
            session_id=session_id,
            approval_policy=approval,
            max_steps=runtime_config.max_steps,
            max_new_tokens=runtime_config.max_new_tokens,
            secret_env_names=configured_secret_names,
            sandbox_config=runtime_config.sandbox,
        )
    return RepoHarness(
        model_client=model,
        workspace=workspace,
        session_store=store,
        approval_policy=approval,
        max_steps=runtime_config.max_steps,
        max_new_tokens=runtime_config.max_new_tokens,
        secret_env_names=configured_secret_names,
        sandbox_config=runtime_config.sandbox,
    )


def build_arg_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Minimal coding agent for Ollama, OpenAI-compatible, Chat Completions-compatible, Anthropic-compatible, or DeepSeek models.",
        epilog="Advanced memory packs: repo-harness memory export/import/inspect/validate",
    )
    parser.set_defaults(
        _provider_explicit=False,
        _model_explicit=False,
        _base_url_explicit=False,
        _max_steps_explicit=False,
        _max_new_tokens_explicit=False,
    )
    parser.add_argument("prompt", nargs="*", help="Optional one-shot prompt.")
    parser.add_argument("--cwd", default=".", help="Workspace directory.")
    parser.add_argument(
        "--provider",
        choices=provider_choices(),
        default="openai",
        action=_ExplicitStoreAction,
        help="Model backend to use.",
    )
    parser.add_argument(
        "--model",
        default=None,
        action=_ExplicitStoreAction,
        help="Model name override. Defaults to qwen3.5:4b for Ollama, OPENAI_MODEL for openai, CHAT_COMPLETIONS_MODEL for chat-completions, ANTHROPIC_MODEL for anthropic, and DEEPSEEK_MODEL for deepseek when set.",
    )
    parser.add_argument("--config", default=None, help="Path to .repo-harness.toml.")
    parser.add_argument("--host", default=DEFAULT_OLLAMA_HOST, help="Ollama server URL.")
    parser.add_argument(
        "--base-url",
        default=None,
        action=_ExplicitStoreAction,
        help="Provider API base URL for openai, chat-completions, anthropic, or deepseek.",
    )
    parser.add_argument("--ollama-timeout", type=int, default=300, help="Ollama request timeout in seconds.")
    parser.add_argument("--openai-timeout", type=int, default=300, help="OpenAI-compatible request timeout in seconds.")
    parser.add_argument("--sandbox", choices=("off", "best_effort", "read_only", "required"), default=None, help="Sandbox mode for run_shell.")
    parser.add_argument("--sandbox-backend", default=None, help="Sandbox backend name.")
    parser.add_argument("--repl", action="store_true", help="Use the interactive REPL.")
    parser.add_argument("--resume", default=None, help="Session id to resume or 'latest'.")
    parser.add_argument("--approval", choices=("ask", "auto", "never"), default="ask", help="Approval policy for risky tools.")
    parser.add_argument("--trust-session", action="store_true", help="Trust all risky tools for this session (equivalent to --approval auto, but preserves audit trail).")
    parser.add_argument(
        "--secret-env-name",
        dest="secret_env_names",
        action="append",
        default=[],
        help="Extra environment variable names to treat as secrets for trace/report redaction.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        action=_ExplicitStoreAction,
        help="Maximum tool/model iterations per request.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=None,
        action=_ExplicitStoreAction,
        help="Maximum model output tokens per step.",
    )
    parser.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature sent to Ollama.")
    parser.add_argument("--top-p", type=float, default=0.9, help="Top-p sampling value sent to Ollama.")
    return parser


def main(argv=None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "memory":
        return handle_memory_command(raw_argv[1:])
    if raw_argv and raw_argv[0] == "provider":
        from .provider_setup import run_provider_command

        return run_provider_command(raw_argv[1:], workspace_root=Path.cwd())
    if raw_argv and raw_argv[0] == "auto-issue-fix":
        from .auto_issue_fix import handle_auto_issue_fix_command

        return handle_auto_issue_fix_command(raw_argv[1:])

    args = build_arg_parser().parse_args(raw_argv)
    agent = build_agent(args)

    from .repl_display import ReplDisplay

    no_color = os.environ.get("NO_COLOR") is not None
    display = ReplDisplay(no_color=no_color)
    agent._display = display
    display.show_welcome(agent)

    # prompt_toolkit: 行编辑、历史、slash 命令补全
    _pt_session = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory

        _slash_commands = [
            "/help", "/skills", "/skill", "/plan", "/plan-exit", "/mode",
            "/usage", "/model", "/history", "/context", "/compact",
            "/working-memory", "/memory", "/memory_explain", "/remember",
            "/memory review", "/memory organize", "/agents", "/subagent",
            "/auto-issue-fix", "/session", "/reset", "/exit",
        ]
        _pt_completer = WordCompleter(_slash_commands, ignore_case=True)
        _pt_history_file = Path(agent.workspace.cwd) / ".repo-harness" / "input_history"
        _pt_history_file.parent.mkdir(parents=True, exist_ok=True)
        _pt_session = PromptSession(
            history=FileHistory(str(_pt_history_file)),
            completer=_pt_completer,
        )
    except Exception:
        pass

    def _read_input(prompt_text):
        if _pt_session is not None:
            try:
                return _pt_session.prompt(prompt_text)
            except Exception:
                pass
        return input(prompt_text)

    if args.prompt:
        # one-shot 模式：只跑一次 ask，不进入 REPL 循环。
        prompt = " ".join(args.prompt).strip()
        if prompt:
            try:
                final = ""
                for event in agent.engine.run_turn(prompt):
                    if event["type"] in {"final", "stop"}:
                        final = event["content"]
                display.show_response(final)
            except RuntimeError as exc:
                display.show_error(str(exc))
                return 1
        return 0

    while True:
        # 交互模式：每次读取一条用户输入，交给同一个 agent，
        # 因此 session history 和 working memory 会跨轮延续。
        try:
            user_input = _read_input("\nrepo-harness> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not user_input:
            continue

        # Slash 命令处理
        handled, should_exit, output = handle_repl_command(agent, user_input, interactive=True)
        if handled:
            if output:
                # 增强特定 slash 命令的输出格式
                if user_input == "/help":
                    display.show_table("Commands", display.build_help_table())
                elif user_input == "/usage":
                    display.show_table("Usage", display.build_usage_table(agent))
                elif user_input == "/history":
                    display.show_table("History", display.build_history_table(agent))
                else:
                    display.show_slash_output(user_input, output)
            if should_exit:
                return 0
            continue
        if user_input.startswith("/subagent"):
            run_subagent(agent, user_input[len("/subagent"):].strip(), display=display)
            continue
        if user_input in {"/memory_pack", "/memory-pack"}:
            run_memory_pack_menu(agent.workspace.cwd, display=display)
            continue
        if user_input == "/memory review":
            run_memory_review(agent, display=display)
            continue
        if user_input.startswith("/remember"):
            text = user_input[len("/remember"):].strip()
            run_remember(agent, text, display=display)
            continue

        # 普通消息：消费事件流，实时显示工具调用和结果
        display.show_user_input(user_input)
        try:
            for event in agent.engine.run_turn(user_input):
                etype = event.get("type", "")
                if etype == "tool_call":
                    display.show_tool_call(event.get("name", "?"), event.get("args", {}))
                elif etype == "tool_result":
                    metadata = event.get("metadata", {})
                    status = metadata.get("tool_status", "success")
                    display.show_tool_result(event.get("name", "?"), event.get("content", ""), status=status)
                elif etype == "final":
                    display.show_response(event.get("content", ""))
                elif etype == "stop":
                    display.show_error(event.get("content", "Stopped"))
                elif etype == "retry":
                    display.show_thinking("retrying")
                elif etype == "model_requested":
                    display.show_thinking("thinking")

            display.show_status(agent)
            notice = _memory_self_iteration_notice(agent)
            if notice:
                print(notice)
        except RuntimeError as exc:
            display.show_error(str(exc))


