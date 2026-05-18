"""Subagent tool module."""

AGENT_TOOL_NAMES = {"agent", "send_message", "task_stop"}
AGENT_TOOL_SPECS = {
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
AGENT_TOOL_EXAMPLES = {
    "agent": '<tool>{"name":"agent","args":{"task":"inspect README","type":"Explore"}}</tool>',
    "send_message": '<tool>{"name":"send_message","args":{"id":"agent_1","message":"continue"}}</tool>',
    "task_stop": '<tool>{"name":"task_stop","args":{"id":"agent_1"}}</tool>',
}


def validate_agent_tool(agent, name, args):
    del agent
    args = args or {}
    if name == "agent" and not str(args.get("task", "")).strip():
        raise ValueError("task must not be empty")
    if name in {"send_message", "task_stop"} and not str(args.get("id", "")).strip():
        raise ValueError("id must not be empty")


def tool_agent(agent, args):
    return agent.tool_agent(args)


def tool_send_message(agent, args):
    return agent.tool_send_message(args)


def tool_task_stop(agent, args):
    return agent.tool_task_stop(args)

