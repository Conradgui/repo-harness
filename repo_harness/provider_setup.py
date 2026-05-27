"""Provider setup and diagnostics helpers.

This module keeps provider onboarding separate from the runtime startup path.
It never stores API key values; it only records the environment variable name
that RepoHarness should read at runtime.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
import sys
from pathlib import Path
import urllib.parse

from .config import CONFIG_FILE_NAME, DEFAULT_PROVIDER_PROFILES, resolve_runtime_config
from .models import AnthropicCompatibleModelClient, ChatCompletionsCompatibleModelClient, OllamaModelClient, OpenAICompatibleModelClient
from .provider_registry import PROVIDER_REGISTRY, provider_choices, provider_endpoint_hints
from .workspace import WorkspaceContext


PROVIDER_ENDPOINT_HINTS = provider_endpoint_hints()
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_SHAPE_RE = re.compile(
    r"(Bearer\s+)[^\s]+|"
    r"\b(?:sk|gho|ghp|github_pat|tp)[_-][A-Za-z0-9_=-]{6,}|"
    r"\b(?:token|api[_-]?key|cookie|authorization)\s*[:=]\s*[^\s]+",
    re.I,
)


@dataclass(frozen=True)
class ProviderDoctorResult:
    ok: bool
    provider: str
    model: str
    base_url: str
    api_key_env: str
    key_present: bool
    summary: str
    detail: str = ""

    def render(self) -> str:
        lines = [
            "Provider doctor:",
            f"- status: {'ok' if self.ok else 'blocked'}",
            f"- provider: {_redact_field(self.provider)}",
            f"- model: {_redact_field(self.model) or '-'}",
            f"- base URL: {_redact_field(self.base_url) or '-'}",
            f"- api key env: {_redact_field(self.api_key_env) or '-'}",
            f"- key present: {'yes' if self.key_present else 'no'}",
            f"- summary: {_redact_field(self.summary)}",
        ]
        if self.detail:
            lines.append(f"- detail: {_redact_diagnostic_text(self.detail)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ProviderProbeResult:
    ok: bool
    provider: str
    model: str
    base_url: str
    api_key_env: str
    key_present: bool
    summary: str
    detail: str = ""

    def render(self) -> str:
        lines = [
            "Provider probe:",
            f"- status: {'ok' if self.ok else 'blocked'}",
            f"- recommended provider: {_redact_field(self.provider) or '-'}",
            f"- model: {_redact_field(self.model) or '-'}",
            f"- base URL: {_redact_field(self.base_url) or '-'}",
            f"- api key env: {_redact_field(self.api_key_env) or '-'}",
            f"- key present: {'yes' if self.key_present else 'no'}",
            f"- summary: {_redact_field(self.summary)}",
        ]
        if self.detail:
            lines.append(f"- detail: {_redact_diagnostic_text(self.detail)}")
        return "\n".join(lines)


def _redact_diagnostic_text(text: str) -> str:
    return SECRET_SHAPE_RE.sub(lambda match: (match.group(1) or "") + "<redacted>", str(text))


def _redact_field(value: str) -> str:
    return _redact_diagnostic_text(str(value or ""))


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _validate_provider(provider: str) -> str:
    provider = str(provider or "").strip()
    if provider not in DEFAULT_PROVIDER_PROFILES:
        allowed = ", ".join(sorted(DEFAULT_PROVIDER_PROFILES))
        raise ValueError(f"provider must be one of: {allowed}")
    return provider


def _validate_api_key_env(api_key_env: str) -> None:
    if not api_key_env:
        raise ValueError("api_key_env must be an environment variable name")
    value = str(api_key_env)
    if not ENV_NAME_RE.fullmatch(value) or SECRET_SHAPE_RE.search(value):
        raise ValueError("api_key_env must be an environment variable name, not an API key value")


def _validate_base_url(base_url: str) -> str:
    value = str(base_url or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must not include credentials, query, or fragment")
    return value


def _strip_known_endpoint(base_url: str, provider: str) -> str:
    value = _validate_base_url(base_url).rstrip("/")
    suffix = PROVIDER_ENDPOINT_HINTS.get(provider, "")
    if suffix and value.endswith(suffix):
        value = value[: -len(suffix)].rstrip("/")
    return value


def detect_provider_from_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().lower().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    if host == "api.deepseek.com":
        return "deepseek"
    if value.endswith("/chat/completions"):
        return "chat-completions"
    if value.endswith("/responses"):
        return "openai"
    if value.endswith("/messages"):
        return "anthropic"
    if value.endswith("/api/generate") or "11434" in value:
        return "ollama"
    if host == "api.openai.com":
        return "openai"
    if host == "api.anthropic.com":
        return "anthropic"
    if "xiaomimimo.com" in host:
        return "chat-completions"
    return ""


def build_provider_setup_toml(*, provider: str, model: str, base_url: str, api_key_env: str) -> str:
    provider = _validate_provider(provider)
    model = str(model).strip()
    api_key_env = str(api_key_env).strip()
    base_url = _strip_known_endpoint(base_url, provider)
    default = DEFAULT_PROVIDER_PROFILES.get(provider, DEFAULT_PROVIDER_PROFILES["openai"])
    client = default.get("client", provider)
    if provider != "ollama":
        _validate_api_key_env(api_key_env)

    if provider == "ollama":
        return "\n".join(
            [
                f"provider = {_toml_string(provider)}",
                "",
                f"[providers.{provider}]",
                f"client = {_toml_string(client)}",
                f"model = {_toml_string(model)}",
                f"base_url = {_toml_string(base_url)}",
                "",
            ]
        )

    return "\n".join(
        [
            f"provider = {_toml_string(provider)}",
            "",
            f"[providers.{provider}]",
            f"client = {_toml_string(client)}",
            f"model = {_toml_string(model)}",
            f"base_url = {_toml_string(base_url)}",
            f"api_key_env = {_toml_string(api_key_env)}",
            "",
        ]
    )


def _provider_section_lines(*, provider: str, model: str, base_url: str, api_key_env: str) -> list[str]:
    rendered = build_provider_setup_toml(provider=provider, model=model, base_url=base_url, api_key_env=api_key_env)
    lines = rendered.splitlines()
    return lines[2:] if len(lines) > 2 else lines


def _provider_section_values(*, provider: str, model: str, base_url: str, api_key_env: str) -> dict[str, str]:
    provider = _validate_provider(provider)
    base_url = _strip_known_endpoint(base_url, provider)
    default = DEFAULT_PROVIDER_PROFILES.get(provider, DEFAULT_PROVIDER_PROFILES["openai"])
    values = {
        "client": _toml_string(default.get("client", provider)),
        "model": _toml_string(str(model).strip()),
        "base_url": _toml_string(base_url),
    }
    if provider != "ollama":
        api_key_env = str(api_key_env).strip()
        _validate_api_key_env(api_key_env)
        values["api_key_env"] = _toml_string(api_key_env)
    return values


def _is_section_header(line: str) -> bool:
    stripped = _section_header_text(line)
    return stripped.startswith("[") and stripped.endswith("]")


def _section_header_text(line: str) -> str:
    stripped = line.strip()
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].rstrip()
    return stripped


def _section_name(line: str) -> str:
    stripped = _section_header_text(line)
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return ""
    return stripped.strip("[]").strip()


def _is_provider_line(line: str) -> bool:
    return bool(re.match(r"^\s*provider\s*=", line))


def _toml_key_name(line: str) -> str:
    match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*=", line)
    return match.group(2) if match else ""


def _replace_toml_value(line: str, value: str) -> str:
    match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*=\s*)(.*)$", line)
    if not match:
        return line
    suffix = ""
    existing_value = match.group(4)
    if "#" in existing_value:
        before_comment, comment = existing_value.split("#", 1)
        if before_comment.rstrip():
            suffix = "  #" + comment
    return f"{match.group(1)}{match.group(2)}{match.group(3)}{value}{suffix}"


def _merge_provider_section_lines(
    section: list[str],
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> list[str]:
    values = _provider_section_values(provider=provider, model=model, base_url=base_url, api_key_env=api_key_env)
    merged = [section[0]]
    seen: set[str] = set()
    for line in section[1:]:
        key = _toml_key_name(line)
        if key in values:
            if key in seen:
                continue
            merged.append(_replace_toml_value(line, values[key]))
            seen.add(key)
            continue
        merged.append(line)
    for key, value in values.items():
        if key not in seen:
            merged.append(f"{key} = {value}")
    return merged


def _merge_provider_config_text(existing: str, *, provider: str, model: str, base_url: str, api_key_env: str) -> str:
    provider = _validate_provider(provider)
    lines = existing.splitlines()
    provider_line = f"provider = {_toml_string(provider)}"
    target_name = f"providers.{provider}"
    section_lines = _provider_section_lines(provider=provider, model=model, base_url=base_url, api_key_env=api_key_env)

    provider_line_index = None
    for index, line in enumerate(lines):
        if _is_section_header(line):
            break
        if _is_provider_line(line):
            provider_line_index = index
            break
    if provider_line_index is None:
        lines.insert(0, provider_line)
        if len(lines) > 1 and lines[1].strip():
            lines.insert(1, "")
    else:
        lines[provider_line_index] = provider_line

    start = None
    for index, line in enumerate(lines):
        if _section_name(line) == target_name:
            start = index
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(section_lines)
    else:
        end = start + 1
        while end < len(lines) and not _is_section_header(lines[end]):
            end += 1
        lines[start:end] = _merge_provider_section_lines(
            lines[start:end],
            provider=provider,
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
        )

    return "\n".join(lines).rstrip() + "\n"


def classify_provider_error(message: str) -> str:
    text = str(message or "").lower()
    if "401" in text or "invalid api key" in text or "unauthorized" in text:
        return "API key is missing, invalid, expired, or RepoHarness is reading the wrong environment variable."
    if "404" in text or "not found" in text:
        return "The provider and endpoint likely do not match. Check whether the vendor uses /responses, /chat/completions, or /messages."
    if "429" in text or "rate" in text:
        return "The provider rate limit was reached. Retry later or lower request frequency."
    if "model" in text and ("not" in text or "invalid" in text):
        return "The configured model name may not be available for this API key or endpoint."
    return "The provider request failed. Check base URL, model name, API key environment variable, and network access."


def _probe_candidate_order(base_url: str) -> list[str]:
    candidates = ["openai", "chat-completions", "anthropic", "ollama"]
    if "deepseek" in str(base_url).lower():
        candidates.insert(candidates.index("anthropic"), "deepseek")
    detected = detect_provider_from_base_url(base_url)
    if detected in candidates:
        candidates.remove(detected)
        candidates.insert(0, detected)
    return candidates


def _probe_client(provider: str, *, model: str, base_url: str, api_key: str):
    base_url = _strip_known_endpoint(base_url, provider)
    if provider == "openai":
        return OpenAICompatibleModelClient(model=model, base_url=base_url, api_key=api_key, temperature=0.0, timeout=10)
    if provider == "chat-completions":
        return ChatCompletionsCompatibleModelClient(model=model, base_url=base_url, api_key=api_key, temperature=0.0, timeout=10)
    if provider in {"anthropic", "deepseek"}:
        return AnthropicCompatibleModelClient(model=model, base_url=base_url, api_key=api_key, temperature=0.0, timeout=10)
    return OllamaModelClient(model=model, host=base_url, temperature=0.0, top_p=1.0, timeout=10)


def probe_provider_endpoint(
    *,
    base_url: str,
    model: str,
    api_key_env: str = "",
    environment: dict | None = None,
    smoke: bool = False,
) -> ProviderProbeResult:
    """Try supported provider protocols and recommend the first working one."""
    base_url = _validate_base_url(base_url)
    model = str(model or "").strip()
    api_key_env = str(api_key_env or "").strip()
    if api_key_env:
        _validate_api_key_env(api_key_env)
    environment = dict(os.environ if environment is None else environment)
    key_value = environment.get(api_key_env, "") if api_key_env else ""
    key_present = bool(key_value) or not api_key_env
    if not base_url:
        return ProviderProbeResult(
            ok=False,
            provider="",
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            key_present=key_present,
            summary="base URL is required",
        )
    if not model:
        return ProviderProbeResult(
            ok=False,
            provider="",
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            key_present=key_present,
            summary="model is required",
        )

    detected = detect_provider_from_base_url(base_url)
    if not smoke:
        if not detected:
            return ProviderProbeResult(
                ok=False,
                provider="",
                model=model,
                base_url=base_url,
                api_key_env=api_key_env,
                key_present=key_present,
                summary="could not infer provider from base URL; pass an explicit endpoint path or run probe with --smoke",
            )
        entry = PROVIDER_REGISTRY[detected]
        if entry.default_api_key_env and not key_value:
            return ProviderProbeResult(
                ok=False,
                provider=detected,
                model=model,
                base_url=_strip_known_endpoint(base_url, detected),
                api_key_env=api_key_env,
                key_present=False,
                summary=f"{api_key_env or entry.default_api_key_env} missing",
                detail="Set the environment variable or pass --api-key-env with the configured variable name.",
            )
        return ProviderProbeResult(
            ok=True,
            provider=detected,
            model=model,
            base_url=_strip_known_endpoint(base_url, detected),
            api_key_env=api_key_env,
            key_present=key_present,
            summary="provider inferred from base URL; live smoke request was skipped",
        )

    first_detail = ""
    for provider in _probe_candidate_order(base_url):
        entry = PROVIDER_REGISTRY[provider]
        if entry.default_api_key_env and not key_value:
            return ProviderProbeResult(
                ok=False,
                provider=provider,
                model=model,
                base_url=base_url,
                api_key_env=api_key_env,
                key_present=False,
                summary=f"{api_key_env or entry.default_api_key_env} missing",
                detail="Set the environment variable or pass --api-key-env with the configured variable name.",
            )
        try:
            client = _probe_client(provider, model=model, base_url=base_url, api_key=key_value)
            client.complete("Reply with exactly: ok", max_new_tokens=16)
        except Exception as exc:  # noqa: BLE001 - probe must classify all provider failures.
            detail = str(exc)
            if not first_detail:
                first_detail = detail
            lowered = detail.lower()
            if "401" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
                return ProviderProbeResult(
                    ok=False,
                    provider="",
                    model=model,
                    base_url=base_url,
                    api_key_env=api_key_env,
                    key_present=key_present,
                    summary=f"authentication failed while testing {provider}: {classify_provider_error(detail)}",
                    detail=detail,
                )
            if "404" in lowered or "not found" in lowered:
                continue
            if "429" in lowered or "rate" in lowered or "500" in lowered or "502" in lowered or "503" in lowered or "504" in lowered:
                return ProviderProbeResult(
                    ok=False,
                    provider=provider,
                    model=model,
                    base_url=base_url,
                    api_key_env=api_key_env,
                    key_present=key_present,
                    summary=classify_provider_error(detail),
                    detail=detail,
                )
            continue
        return ProviderProbeResult(
            ok=True,
            provider=provider,
            model=model,
            base_url=_strip_known_endpoint(base_url, provider),
            api_key_env=api_key_env,
            key_present=key_present,
            summary=f"{provider} smoke request succeeded",
        )

    return ProviderProbeResult(
        ok=False,
        provider="",
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        key_present=key_present,
        summary="no supported provider protocol succeeded",
        detail=first_detail,
    )


def _args_for_workspace(workspace_root: Path):
    return argparse.Namespace(
        cwd=str(workspace_root),
        provider="openai",
        _provider_explicit=False,
        model=None,
        _model_explicit=False,
        base_url=None,
        _base_url_explicit=False,
        config=None,
        max_steps=None,
        _max_steps_explicit=False,
        max_new_tokens=None,
        _max_new_tokens_explicit=False,
        sandbox=None,
        sandbox_backend=None,
    )


def provider_doctor(*, workspace_root: str | Path = ".", smoke: bool = False) -> ProviderDoctorResult:
    workspace_root = Path(workspace_root)
    config = resolve_runtime_config(_args_for_workspace(workspace_root), WorkspaceContext.build(workspace_root))
    profile = config.provider_profile
    key_present = True
    if profile.api_key_env:
        key_present = bool(config.environment.get(profile.api_key_env))
    if not key_present:
        return ProviderDoctorResult(
            ok=False,
            provider=config.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            key_present=False,
            summary=f"{profile.api_key_env} missing",
            detail="Set the environment variable or update api_key_env in .repo-harness.toml.",
        )
    if not smoke:
        return ProviderDoctorResult(
            ok=True,
            provider=config.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            key_present=key_present,
            summary="configuration is readable; smoke request was skipped",
        )

    from .cli import _build_model_client

    try:
        client = _build_model_client(_args_for_workspace(workspace_root), runtime_config=config)
        client.complete("Reply with exactly: ok", max_new_tokens=16)
    except Exception as exc:  # noqa: BLE001 - diagnostic command should explain provider failures.
        return ProviderDoctorResult(
            ok=False,
            provider=config.provider,
            model=profile.model,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            key_present=key_present,
            summary=classify_provider_error(str(exc)),
            detail=_redact_diagnostic_text(str(exc)),
        )

    return ProviderDoctorResult(
        ok=True,
        provider=config.provider,
        model=profile.model,
        base_url=profile.base_url,
        api_key_env=profile.api_key_env,
        key_present=key_present,
        summary="smoke request succeeded",
    )


def write_provider_config(
    *,
    workspace_root: str | Path,
    provider: str,
    model: str,
    base_url: str,
    api_key_env: str,
) -> Path:
    workspace = WorkspaceContext.build(workspace_root)
    path = Path(workspace.repo_root) / CONFIG_FILE_NAME
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered = _merge_provider_config_text(existing, provider=provider, model=model, base_url=base_url, api_key_env=api_key_env)
    path.write_text(rendered, encoding="utf-8")
    return path


def run_provider_command(argv: list[str] | None = None, *, input_func=input, workspace_root: str | Path = ".") -> int:
    parser = argparse.ArgumentParser(prog="repo-harness provider")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--smoke", action="store_true", help="Run a real minimal provider request.")

    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("--base-url", default="")
    probe_parser.add_argument("--model", default="")
    probe_parser.add_argument("--api-key-env", default="")
    probe_parser.add_argument("--write", action="store_true", help="Write the detected provider profile to .repo-harness.toml.")
    probe_parser.add_argument("--smoke", action="store_true", help="Send a real minimal provider request while probing.")
    probe_parser.add_argument(
        "--allow-live-probe",
        action="store_true",
        help="Alias for --smoke; sends a real minimal provider request.",
    )

    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--provider", choices=provider_choices(), default="")
    setup_parser.add_argument("--base-url", default="")
    setup_parser.add_argument("--model", default="")
    setup_parser.add_argument("--api-key-env", default="")

    args = parser.parse_args(argv)
    workspace_root = Path(workspace_root)
    if args.command == "doctor":
        result = provider_doctor(workspace_root=workspace_root, smoke=args.smoke)
        print(result.render())
        return 0 if result.ok else 1

    if args.command == "probe":
        base_url = args.base_url or input_func("Provider base URL: ").strip()
        model = args.model or input_func("Model: ").strip()
        api_key_env = args.api_key_env or input_func("API key environment variable: ").strip()
        try:
            result = probe_provider_endpoint(
                base_url=base_url,
                model=model,
                api_key_env=api_key_env,
                environment=os.environ,
                smoke=bool(args.smoke or args.allow_live_probe),
            )
        except ValueError as exc:
            print(f"provider probe: {_redact_field(str(exc))}", file=sys.stderr)
            return 2
        print(result.render())
        if not result.ok:
            return 1
        if args.write:
            path = write_provider_config(
                workspace_root=workspace_root,
                provider=result.provider,
                model=result.model,
                base_url=result.base_url,
                api_key_env=result.api_key_env,
            )
            print(f"provider probe: wrote {path}")
            print("provider probe: stored the API key environment variable name only; no secret value was written.")
        return 0

    base_url = args.base_url or input_func("Provider base URL: ").strip()
    provider = args.provider or detect_provider_from_base_url(base_url)
    if not provider:
        print(
            "provider setup: could not infer provider from base URL; pass --provider or run provider probe first",
            file=sys.stderr,
        )
        return 2
    default = DEFAULT_PROVIDER_PROFILES.get(provider, DEFAULT_PROVIDER_PROFILES["chat-completions"])
    model = args.model or input_func(f"Model [{default['model']}]: ").strip() or default["model"]
    api_key_env = args.api_key_env
    if provider != "ollama" and not api_key_env:
        api_key_env = input_func(f"API key environment variable [{default['api_key_env']}]: ").strip() or default["api_key_env"]
    try:
        path = write_provider_config(
            workspace_root=workspace_root,
            provider=provider,
            model=model,
            base_url=base_url or default["base_url"],
            api_key_env=api_key_env,
        )
    except ValueError as exc:
        print(f"provider setup: {exc}", file=sys.stderr)
        return 2
    print(f"provider setup: wrote {path}")
    print("provider setup: stored the API key environment variable name only; no secret value was written.")
    return 0
