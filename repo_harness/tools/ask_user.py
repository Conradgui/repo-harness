"""ask_user tool module."""

ASK_USER_TOOL_SPECS = {
    "ask_user": {
        "schema": {"question": "str", "choices": "list=[]"},
        "risky": False,
        "description": "Ask the user a short question and record the answer.",
    }
}

ASK_USER_TOOL_EXAMPLES = {
    "ask_user": '<tool>{"name":"ask_user","args":{"question":"Proceed?","choices":["yes","no"]}}</tool>'
}


def validate_ask_user_tool(name, args):
    if name != "ask_user":
        return
    if not str((args or {}).get("question", "")).strip():
        raise ValueError("question must not be empty")


def tool_ask_user(agent, args):
    return agent.tool_ask_user(args)

