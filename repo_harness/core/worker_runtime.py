"""Child runtime construction for workers."""


def build_child_runtime(parent, subagent_type, write_scope):
    from ..runtime import RepoHarness

    # A child must never be MORE privileged than its parent: an Explore child
    # is always read-only, and a child of a read-only parent stays read-only.
    # Otherwise a read_only parent (e.g. Auto Issue Fix on a clone that
    # declared sandbox=read_only) could spawn a writable worker and bypass the
    # declared boundary through write_file/patch_file.
    read_only = subagent_type == "Explore" or bool(getattr(parent, "read_only", False))
    if subagent_type == "worker" and not write_scope:
        raise ValueError("worker write_scope must not be empty")
    model_client = _child_model_client(parent, subagent_type, write_scope)
    # The parent run and its current span are captured at spawn time, not when
    # the worker's ask() later runs in its own thread -- the parent's
    # current_run_id is cleared once its own turn finishes.
    child = RepoHarness(
        model_client=model_client,
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
        model_client_factory=getattr(parent, "model_client_factory", None),
        parent_run_id=getattr(parent, "current_run_id", "") or "",
        parent_span_id=parent._last_trace_span_id.get(
            getattr(parent, "current_run_id", ""), ""
        ),
    )
    child.tool_profiles = dict(parent.tool_profiles)
    child.set_tool_profile("readonly" if read_only else "worker")
    return child


def _child_model_client(parent, subagent_type, write_scope):
    factory = getattr(parent, "model_client_factory", None)
    if not callable(factory):
        return parent.model_client
    kwargs = {
        "task": "",
        "workspace": parent.workspace,
        "subagent_type": subagent_type,
        "write_scope": list(write_scope or ()),
        "parent": parent,
    }
    try:
        return factory(**kwargs)
    except TypeError:
        try:
            return factory()
        except TypeError:
            return parent.model_client
