"""Provider registry shared by config, setup, diagnostics, and CLI.

RepoHarness keeps provider clients small and explicit, but the metadata used to
select and explain those clients should live in one place.  This registry is
the single source of truth for supported provider names, default profiles, and
endpoint probes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRegistryEntry:
    name: str
    client: str
    default_model: str
    default_base_url: str
    default_api_key_env: str
    model_env: str
    base_url_env: str
    max_new_tokens: int
    endpoint_path: str
    protocol: str
    supports_prompt_cache: bool = False
    smoke_supported: bool = True
    gateway_compatible: bool = False

    def default_profile(self) -> dict[str, str]:
        return {
            "client": self.client,
            "model": self.default_model,
            "base_url": self.default_base_url,
            "api_key_env": self.default_api_key_env,
        }


PROVIDER_REGISTRY: dict[str, ProviderRegistryEntry] = {
    "openai": ProviderRegistryEntry(
        name="openai",
        client="openai",
        default_model="gpt-5.4",
        default_base_url="https://www.right.codes/codex/v1",
        default_api_key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        base_url_env="OPENAI_API_BASE",
        max_new_tokens=8192,
        endpoint_path="/responses",
        protocol="openai-compatible",
        supports_prompt_cache=True,
        gateway_compatible=True,
    ),
    "chat-completions": ProviderRegistryEntry(
        name="chat-completions",
        client="chat-completions",
        default_model="gpt-5.4",
        default_base_url="https://api.openai.com/v1",
        default_api_key_env="CHAT_COMPLETIONS_API_KEY",
        model_env="CHAT_COMPLETIONS_MODEL",
        base_url_env="CHAT_COMPLETIONS_API_BASE",
        max_new_tokens=8192,
        endpoint_path="/chat/completions",
        protocol="chat-completions-compatible",
        gateway_compatible=True,
    ),
    "anthropic": ProviderRegistryEntry(
        name="anthropic",
        client="anthropic",
        default_model="claude-sonnet-4-6",
        default_base_url="https://www.right.codes/claude/v1",
        default_api_key_env="ANTHROPIC_API_KEY",
        model_env="ANTHROPIC_MODEL",
        base_url_env="ANTHROPIC_API_BASE",
        max_new_tokens=32000,
        endpoint_path="/messages",
        protocol="anthropic-compatible",
    ),
    "deepseek": ProviderRegistryEntry(
        name="deepseek",
        client="anthropic",
        default_model="deepseek-v4-pro",
        default_base_url="https://api.deepseek.com/anthropic",
        default_api_key_env="DEEPSEEK_API_KEY",
        model_env="DEEPSEEK_MODEL",
        base_url_env="DEEPSEEK_API_BASE",
        max_new_tokens=8192,
        endpoint_path="/messages",
        protocol="anthropic-compatible",
    ),
    "ollama": ProviderRegistryEntry(
        name="ollama",
        client="ollama",
        default_model="qwen3.5:4b",
        default_base_url="http://127.0.0.1:11434",
        default_api_key_env="",
        model_env="OLLAMA_MODEL",
        base_url_env="OLLAMA_HOST",
        max_new_tokens=512,
        endpoint_path="/api/generate",
        protocol="ollama",
        smoke_supported=True,
    ),
}


def provider_names() -> tuple[str, ...]:
    return tuple(PROVIDER_REGISTRY)


def provider_choices() -> tuple[str, ...]:
    return tuple(sorted(PROVIDER_REGISTRY))


def default_provider_profiles() -> dict[str, dict[str, str]]:
    return {name: entry.default_profile() for name, entry in PROVIDER_REGISTRY.items()}


def default_max_new_tokens() -> dict[str, int]:
    return {name: entry.max_new_tokens for name, entry in PROVIDER_REGISTRY.items()}


def provider_model_env() -> dict[str, str]:
    return {name: entry.model_env for name, entry in PROVIDER_REGISTRY.items()}


def provider_base_url_env() -> dict[str, str]:
    return {name: entry.base_url_env for name, entry in PROVIDER_REGISTRY.items()}


def provider_endpoint_hints() -> dict[str, str]:
    return {name: entry.endpoint_path for name, entry in PROVIDER_REGISTRY.items()}
