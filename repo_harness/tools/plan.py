"""Plan mode tool module."""

PLAN_TOOL_SPECS = {
    "enter_plan_mode": {
        "schema": {"topic": "str"},
        "risky": False,
        "description": "Enter plan mode and create an active plan artifact.",
    },
    "exit_plan_mode": {
        "schema": {},
        "risky": False,
        "description": "Exit plan mode.",
    },
}
PLAN_TOOL_EXAMPLES = {
    "enter_plan_mode": '<tool>{"name":"enter_plan_mode","args":{"topic":"release"}}</tool>',
    "exit_plan_mode": '<tool>{"name":"exit_plan_mode","args":{}}</tool>',
}


def validate_plan_tool(name, args):
    if name == "enter_plan_mode" and not str((args or {}).get("topic", "")).strip():
        raise ValueError("topic must not be empty")


def tool_enter_plan_mode(agent, args):
    return agent.enter_plan_mode((args or {}).get("topic", "plan"))


def tool_exit_plan_mode(agent, args):
    del args
    return agent.exit_plan_mode()

