"""Runtime configuration loading for RepoHarness."""

from dataclasses import dataclass
import os
from pathlib import Path

from .sandbox import SandboxConfig

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


CONFIG_FILE_NAME = ".repo-harness.toml"

DEFAULT_PROVIDER = "openai"
DEFAULT_MAX_STEPS = 50
DEFAULT_MAX_NEW_TOKENS = {
    "ollama": 512,
    "openai": 8192,
    "anthropic": 8192,
    "deepseek": 8192,
}

DEFAULT_PROVIDER_PROFILES = {
    "openai": {
        "client": "openai",
        "model": "gpt-5.4",
        "base_url": "https://www.right.codes/codex/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "client": "anthropic",
        "model": "claude-sonnet-4-6",
        "base_url": "https://www.right.codes/claude/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "deepseek": {
        "client": "anthropic",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "ollama": {
        "client": "ollama",
        "model": "qwen3.5:4b",
        "base_url": "http://127.0.0.1:11434",
        "api_key_env": "",
    },
}

DEFAULT_OPENAI_MODEL = DEFAULT_PROVIDER_PROFILES["openai"]["model"]
DEFAULT_OPENAI_BASE_URL = DEFAULT_PROVIDER_PROFILES["openai"]["base_url"]
DEFAULT_ANTHROPIC_MODEL = DEFAULT_PROVIDER_PROFILES["anthropic"]["model"]
DEFAULT_ANTHROPIC_BASE_URL = DEFAULT_PROVIDER_PROFILES["anthropic"]["base_url"]
DEFAULT_OLLAMA_MODEL = DEFAULT_PROVIDER_PROFILES["ollama"]["model"]
DEFAULT_OLLAMA_HOST = DEFAULT_PROVIDER_PROFILES["ollama"]["base_url"]

PROVIDER_MODEL_ENV = {
    "openai": "OPENAI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "deepseek": "DEEPSEEK_MODEL",
    "ollama": "OLLAMA_MODEL",
}

PROVIDER_BASE_URL_ENV = {
    "openai": "OPENAI_API_BASE",
    "anthropic": "ANTHROPIC_API_BASE",
    "deepseek": "DEEPSEEK_API_BASE",
    "ollama": "OLLAMA_HOST",
}


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


def _load_toml(path):
    path = Path(path)
    if not path.exists():
        return {}, ""
    with path.open("rb") as handle:
        return tomllib.load(handle), str(path)


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


def _provider_from_sources(args, data):
    if _arg_was_explicit(args, "provider"):
        return str(getattr(args, "provider")).strip()
    env_provider = os.environ.get("REPO_HARNESS_PROVIDER")
    if env_provider:
        return env_provider.strip()
    if data.get("provider"):
        return str(data["provider"]).strip()
    return DEFAULT_PROVIDER


def _toml_provider_profile(data, provider):
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    profile = providers.get(provider, {})
    return profile if isinstance(profile, dict) else {}


def _resolve_profile(args, data, provider):
    defaults = dict(DEFAULT_PROVIDER_PROFILES.get(provider, DEFAULT_PROVIDER_PROFILES[DEFAULT_PROVIDER]))
    toml_profile = _toml_provider_profile(data, provider)
    profile = {**defaults, **{key: value for key, value in toml_profile.items() if value is not None}}

    if os.environ.get(PROVIDER_MODEL_ENV.get(provider, "")):
        profile["model"] = os.environ[PROVIDER_MODEL_ENV[provider]]
    if os.environ.get("REPO_HARNESS_MODEL"):
        profile["model"] = os.environ["REPO_HARNESS_MODEL"]
    if _arg_was_explicit(args, "model") and getattr(args, "model", None):
        profile["model"] = getattr(args, "model")

    provider_base_env = PROVIDER_BASE_URL_ENV.get(provider, "")
    if provider_base_env and os.environ.get(provider_base_env):
        profile["base_url"] = os.environ[provider_base_env]
    if os.environ.get("REPO_HARNESS_BASE_URL"):
        profile["base_url"] = os.environ["REPO_HARNESS_BASE_URL"]
    if _arg_was_explicit(args, "base_url") and getattr(args, "base_url", None):
        profile["base_url"] = getattr(args, "base_url")

    return ProviderProfile(
        name=provider,
        client=str(profile.get("client", provider)).strip(),
        model=str(profile.get("model", "")).strip(),
        base_url=str(profile.get("base_url", "")).strip(),
        api_key_env=str(profile.get("api_key_env", "")).strip(),
    )


def _resolve_max_steps(args, data):
    if _arg_was_explicit(args, "max_steps") and getattr(args, "max_steps", None) is not None:
        return int(getattr(args, "max_steps"))
    if os.environ.get("REPO_HARNESS_MAX_STEPS"):
        return int(os.environ["REPO_HARNESS_MAX_STEPS"])
    if data.get("max_steps") is not None:
        return int(data["max_steps"])
    return DEFAULT_MAX_STEPS


def _resolve_max_new_tokens(args, data, provider):
    if _arg_was_explicit(args, "max_new_tokens") and getattr(args, "max_new_tokens", None) is not None:
        return int(getattr(args, "max_new_tokens"))
    if os.environ.get("REPO_HARNESS_MAX_NEW_TOKENS"):
        return int(os.environ["REPO_HARNESS_MAX_NEW_TOKENS"])
    if data.get("max_new_tokens") is not None:
        return int(data["max_new_tokens"])
    if data.get("max_tokens") is not None:
        return int(data["max_tokens"])
    return DEFAULT_MAX_NEW_TOKENS.get(provider, 512)


def _resolve_sandbox(args, data):
    sandbox_data = data.get("sandbox", {})
    if not isinstance(sandbox_data, dict):
        sandbox_data = {}
    mode = sandbox_data.get("mode", "off")
    backend = sandbox_data.get("backend", "native")
    if os.environ.get("REPO_HARNESS_SANDBOX"):
        mode = os.environ["REPO_HARNESS_SANDBOX"]
    if os.environ.get("REPO_HARNESS_SANDBOX_BACKEND"):
        backend = os.environ["REPO_HARNESS_SANDBOX_BACKEND"]
    if getattr(args, "sandbox", None):
        mode = getattr(args, "sandbox")
    if getattr(args, "sandbox_backend", None):
        backend = getattr(args, "sandbox_backend")
    return SandboxConfig(mode=str(mode).strip(), backend=str(backend).strip())


def resolve_runtime_config(args, workspace):
    data, config_path = _load_toml(_workspace_config_path(args, workspace))
    provider = _provider_from_sources(args, data)
    profile = _resolve_profile(args, data, provider)
    return RepoHarnessConfig(
        provider=provider,
        provider_profile=profile,
        max_steps=_resolve_max_steps(args, data),
        max_new_tokens=_resolve_max_new_tokens(args, data, provider),
        sandbox=_resolve_sandbox(args, data),
        config_path=config_path,
    )
