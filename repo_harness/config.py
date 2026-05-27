"""Runtime configuration loading for RepoHarness."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from .provider_registry import (
    default_max_new_tokens,
    default_provider_profiles,
    provider_base_url_env,
    provider_choices,
    provider_model_env,
)
from .sandbox import SandboxConfig

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


CONFIG_FILE_NAME = ".repo-harness.toml"

DEFAULT_PROVIDER = "openai"
DEFAULT_MAX_STEPS = 50
DEFAULT_MAX_NEW_TOKENS = default_max_new_tokens()
DEFAULT_PROVIDER_PROFILES = default_provider_profiles()

DEFAULT_OPENAI_MODEL = DEFAULT_PROVIDER_PROFILES["openai"]["model"]
DEFAULT_OPENAI_BASE_URL = DEFAULT_PROVIDER_PROFILES["openai"]["base_url"]
DEFAULT_ANTHROPIC_MODEL = DEFAULT_PROVIDER_PROFILES["anthropic"]["model"]
DEFAULT_ANTHROPIC_BASE_URL = DEFAULT_PROVIDER_PROFILES["anthropic"]["base_url"]
DEFAULT_OLLAMA_MODEL = DEFAULT_PROVIDER_PROFILES["ollama"]["model"]
DEFAULT_OLLAMA_HOST = DEFAULT_PROVIDER_PROFILES["ollama"]["base_url"]

PROVIDER_MODEL_ENV = provider_model_env()
PROVIDER_BASE_URL_ENV = provider_base_url_env()


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    client: str
    model: str
    base_url: str
    api_key_env: str = ""


@dataclass(frozen=True)
class RepoHarnessConfig:
    provider: str
    provider_profile: ProviderProfile
    max_steps: int
    max_new_tokens: int
    sandbox: SandboxConfig = SandboxConfig()
    config_path: str = ""
    environment: dict = field(default_factory=dict)


def _load_toml(path):
    if not path:
        return {}, ""
    path = Path(path)
    if not path.exists() or not path.is_file():
        return {}, ""
    with path.open("rb") as handle:
        return tomllib.load(handle), str(path)


def _home_dir():
    for name in ("REPO_HARNESS_HOME", "USERPROFILE", "HOME"):
        value = os.environ.get(name)
        if value:
            return Path(value)
    try:
        return Path.home()
    except RuntimeError:
        return None


def _global_config_path():
    home = _home_dir()
    if home is None:
        return None
    return home / ".repo-harness" / "config.toml"


def _project_env_path(workspace):
    return Path(workspace.repo_root) / ".env"


def _strip_env_quotes(value):
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file(path):
    path = Path(path)
    if not path.exists():
        return {}
    env = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key:
            env[key] = _strip_env_quotes(value)
    return env


def _effective_env(workspace):
    project_env = _load_env_file(_project_env_path(workspace))
    return {**project_env, **dict(os.environ)}


def _merge_config(global_data, project_data):
    merged = dict(global_data or {})
    for key, value in (project_data or {}).items():
        if key == "providers" and isinstance(value, dict):
            providers = dict(merged.get("providers", {}) if isinstance(merged.get("providers"), dict) else {})
            for provider_name, provider_profile in value.items():
                base = dict(providers.get(provider_name, {}) if isinstance(providers.get(provider_name), dict) else {})
                if isinstance(provider_profile, dict):
                    base.update(provider_profile)
                    providers[provider_name] = base
                else:
                    providers[provider_name] = provider_profile
            merged["providers"] = providers
            continue
        if key == "sandbox" and isinstance(value, dict):
            base = dict(merged.get("sandbox", {}) if isinstance(merged.get("sandbox"), dict) else {})
            base.update(value)
            merged["sandbox"] = base
            continue
        merged[key] = value
    return merged


def _workspace_config_path(args, workspace):
    explicit = getattr(args, "config", None)
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = Path(getattr(workspace, "cwd", ".")) / path
        return path
    return Path(workspace.repo_root) / CONFIG_FILE_NAME


def _int_value(value, fallback):
    if value is None or value == "":
        return fallback
    return int(value)


def _arg_was_explicit(args, name):
    marker = f"_{name}_explicit"
    if hasattr(args, marker):
        return bool(getattr(args, marker))
    return getattr(args, name, None) is not None


def _provider_from_sources(args, data, env):
    if _arg_was_explicit(args, "provider"):
        provider = str(getattr(args, "provider")).strip()
    elif env.get("REPO_HARNESS_PROVIDER"):
        provider = env["REPO_HARNESS_PROVIDER"].strip()
    elif data.get("provider"):
        provider = str(data["provider"]).strip()
    else:
        provider = DEFAULT_PROVIDER
    if provider not in DEFAULT_PROVIDER_PROFILES:
        allowed = ", ".join(provider_choices())
        raise ValueError(f"provider must be one of: {allowed}")
    return provider


def _toml_provider_profile(data, provider):
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    profile = providers.get(provider, {})
    return profile if isinstance(profile, dict) else {}


def _resolve_profile(args, data, provider, env):
    defaults = dict(DEFAULT_PROVIDER_PROFILES.get(provider, DEFAULT_PROVIDER_PROFILES[DEFAULT_PROVIDER]))
    toml_profile = _toml_provider_profile(data, provider)
    profile = {**defaults, **{key: value for key, value in toml_profile.items() if value is not None}}

    if env.get(PROVIDER_MODEL_ENV.get(provider, "")):
        profile["model"] = env[PROVIDER_MODEL_ENV[provider]]
    if env.get("REPO_HARNESS_MODEL"):
        profile["model"] = env["REPO_HARNESS_MODEL"]
    if _arg_was_explicit(args, "model") and getattr(args, "model", None):
        profile["model"] = getattr(args, "model")

    provider_base_env = PROVIDER_BASE_URL_ENV.get(provider, "")
    if provider_base_env and env.get(provider_base_env):
        profile["base_url"] = env[provider_base_env]
    if env.get("REPO_HARNESS_BASE_URL"):
        profile["base_url"] = env["REPO_HARNESS_BASE_URL"]
    if _arg_was_explicit(args, "base_url") and getattr(args, "base_url", None):
        profile["base_url"] = getattr(args, "base_url")

    return ProviderProfile(
        name=provider,
        client=str(profile.get("client", provider)).strip(),
        model=str(profile.get("model", "")).strip(),
        base_url=str(profile.get("base_url", "")).strip(),
        api_key_env=str(profile.get("api_key_env", "")).strip(),
    )


def _resolve_max_steps(args, data, env):
    if _arg_was_explicit(args, "max_steps") and getattr(args, "max_steps", None) is not None:
        return int(getattr(args, "max_steps"))
    if env.get("REPO_HARNESS_MAX_STEPS"):
        return int(env["REPO_HARNESS_MAX_STEPS"])
    if data.get("max_steps") is not None:
        return int(data["max_steps"])
    return DEFAULT_MAX_STEPS


def _resolve_max_new_tokens(args, data, provider, env):
    if _arg_was_explicit(args, "max_new_tokens") and getattr(args, "max_new_tokens", None) is not None:
        return int(getattr(args, "max_new_tokens"))
    if env.get("REPO_HARNESS_MAX_NEW_TOKENS"):
        return int(env["REPO_HARNESS_MAX_NEW_TOKENS"])
    if data.get("max_new_tokens") is not None:
        return int(data["max_new_tokens"])
    if data.get("max_tokens") is not None:
        return int(data["max_tokens"])
    return DEFAULT_MAX_NEW_TOKENS.get(provider, 512)


def _resolve_sandbox(args, data, env):
    sandbox_data = data.get("sandbox", {})
    if not isinstance(sandbox_data, dict):
        sandbox_data = {}
    filesystem = sandbox_data.get("filesystem", {})
    if not isinstance(filesystem, dict):
        filesystem = {}
    mode = sandbox_data.get("mode", "off")
    backend = sandbox_data.get("backend", "native")
    if env.get("REPO_HARNESS_SANDBOX"):
        mode = env["REPO_HARNESS_SANDBOX"]
    if env.get("REPO_HARNESS_SANDBOX_BACKEND"):
        backend = env["REPO_HARNESS_SANDBOX_BACKEND"]
    if getattr(args, "sandbox", None):
        mode = getattr(args, "sandbox")
    if getattr(args, "sandbox_backend", None):
        backend = getattr(args, "sandbox_backend")
    return SandboxConfig(
        mode=str(mode).strip(),
        backend=str(backend).strip(),
        workspace_write=bool(sandbox_data.get("workspace_write", True)),
        excluded_commands=tuple(str(item) for item in sandbox_data.get("excluded_commands", []) or []),
        extra_readonly_paths=tuple(str(item) for item in filesystem.get("extra_readonly_paths", []) or []),
        deny_read=tuple(str(item) for item in filesystem.get("deny_read", []) or []),
        deny_write=tuple(str(item) for item in filesystem.get("deny_write", []) or []),
    )


def resolve_runtime_config(args, workspace):
    global_data, global_config_path = _load_toml(_global_config_path() or "")
    project_data, project_config_path = _load_toml(_workspace_config_path(args, workspace))
    data = _merge_config(global_data, project_data)
    env = _effective_env(workspace)
    provider = _provider_from_sources(args, data, env)
    profile = _resolve_profile(args, data, provider, env)
    return RepoHarnessConfig(
        provider=provider,
        provider_profile=profile,
        max_steps=_resolve_max_steps(args, data, env),
        max_new_tokens=_resolve_max_new_tokens(args, data, provider, env),
        sandbox=_resolve_sandbox(args, data, env),
        config_path=project_config_path or global_config_path,
        environment=env,
    )
