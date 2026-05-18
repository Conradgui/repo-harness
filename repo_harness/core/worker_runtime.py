"""Child runtime construction for workers."""


def build_child_runtime(parent, subagent_type, write_scope):
    from ..runtime import RepoHarness

    read_only = subagent_type == "Explore"
    if subagent_type == "worker" and not write_scope:
        raise ValueError("worker write_scope must not be empty")
    child = RepoHarness(
        model_client=parent.model_client,
        workspace=parent.workspace,
        session_store=parent.session_store,
        run_store=parent.run_store,
        approval_policy="auto",
        max_steps=min(parent.max_steps, 8),
        max_new_tokens=parent.max_new_tokens,
        depth=parent.depth + 1,
        max_depth=max(parent.max_depth, parent.depth + 2),
        read_only=read_only,
        secret_env_names=parent.secret_env_names,
        shell_env_allowlist=parent.shell_env_allowlist,
        sandbox_config=parent.sandbox_config,
        write_scope=list(write_scope or ()),
        ask_user_callback=getattr(parent, "ask_user_callback", None),
    )
    child.tool_profiles = dict(parent.tool_profiles)
    child.set_tool_profile("readonly" if read_only else "worker")
    return child
