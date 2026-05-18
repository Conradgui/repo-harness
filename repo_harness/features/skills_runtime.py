"""Execution helpers for RepoHarness skills."""

from __future__ import annotations

from contextlib import contextmanager

from ..core.tool_profiles import ToolSetProfile
from .skills import render_skill_prompt


def invoke_skill(agent, name, arguments=""):
    skill = agent.skills.get(str(name).strip().lstrip("/"))
    if not skill:
        return f"skill not found: {name}"
    prompt = render_skill_prompt(skill, arguments)
    agent.session_event_bus.emit("skill_invoked", _event_payload(skill, arguments, prompt))
    if skill.disable_model_invocation:
        agent.session_event_bus.emit(
            "skill_completed",
            _event_payload(skill, arguments, prompt, status="prompt_only"),
        )
        return prompt
    with _model_override(agent, skill.model), _skill_tool_profile(agent, skill):
        answer = _run_fork(agent, skill, prompt) if skill.context == "fork" else agent.ask(prompt)
    agent.session_event_bus.emit(
        "skill_completed",
        _event_payload(skill, arguments, prompt, status="completed", answer=answer),
    )
    return answer


def _run_fork(agent, skill, prompt):
    child = type(agent)(
        model_client=agent.model_client,
        workspace=agent.workspace,
        session_store=agent.session_store,
        run_store=agent.run_store,
        approval_policy=agent.approval_policy,
        max_steps=agent.max_steps,
        max_new_tokens=agent.max_new_tokens,
        depth=agent.depth,
        max_depth=agent.max_depth,
        read_only=agent.read_only,
        shell_env_allowlist=agent.shell_env_allowlist,
        secret_env_names=agent.secret_env_names,
        feature_flags=agent.feature_flags,
        sandbox_config=agent.sandbox_config,
    )
    with _model_override(child, skill.model), _skill_tool_profile(child, skill):
        answer = child.ask(prompt)
    agent.session_event_bus.emit(
        "skill_fork_completed",
        {"skill": skill.name, "child_session_id": child.session["id"]},
    )
    return answer


def _event_payload(skill, arguments, prompt, status="", answer=""):
    payload = {
        "skill": skill.name,
        "name": skill.name,
        "source": skill.source,
        "context": skill.context,
        "arguments": str(arguments),
        "allowed_tools": list(skill.allowed_tools),
        "prompt_chars": len(prompt),
        "model_override": skill.model,
    }
    if status:
        payload["status"] = status
    if answer:
        payload["answer_chars"] = len(str(answer))
    return payload


@contextmanager
def _skill_tool_profile(agent, skill):
    if not skill.allowed_tools:
        yield
        return
    previous = agent.active_tool_profile.name
    profile_name = f"skill:{skill.name}"
    allowed = frozenset(name for name in skill.allowed_tools if name in agent.tools)
    agent.tool_profiles[profile_name] = ToolSetProfile(profile_name, allowed)
    agent.set_tool_profile(profile_name)
    try:
        yield
    finally:
        agent.set_tool_profile(previous)
        agent.tool_profiles.pop(profile_name, None)


@contextmanager
def _model_override(agent, model):
    if not model:
        yield
        return
    sentinel = object()
    previous = getattr(agent.model_client, "model", sentinel)
    setattr(agent.model_client, "model", model)
    try:
        yield
    finally:
        if previous is sentinel:
            delattr(agent.model_client, "model")
        else:
            setattr(agent.model_client, "model", previous)
