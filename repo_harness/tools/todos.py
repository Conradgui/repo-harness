"""Todo ledger tool module."""

TODO_TOOL_SPECS = {
    "todo_add": {
        "schema": {"text": "str", "status": "str='pending'"},
        "risky": False,
        "description": "Add an item to the session todo ledger.",
    },
    "todo_update": {
        "schema": {"id": "str", "text": "str?", "status": "str?"},
        "risky": False,
        "description": "Update an item in the session todo ledger.",
    },
    "todo_list": {
        "schema": {},
        "risky": False,
        "description": "List the session todo ledger.",
    },
}
TODO_TOOL_EXAMPLES = {
    "todo_add": '<tool>{"name":"todo_add","args":{"text":"Run tests","status":"pending"}}</tool>',
    "todo_update": '<tool>{"name":"todo_update","args":{"id":"todo_1","status":"completed"}}</tool>',
    "todo_list": '<tool>{"name":"todo_list","args":{}}</tool>',
}


def validate_todo_tool(name, args):
    args = args or {}
    if name == "todo_add" and not str(args.get("text", "")).strip():
        raise ValueError("text must not be empty")
    if name == "todo_update" and not str(args.get("id", "")).strip():
        raise ValueError("id must not be empty")


def tool_todo_add(agent, args):
    return agent.tool_todo_add(args)


def tool_todo_update(agent, args):
    return agent.tool_todo_update(args)


def tool_todo_list(agent, args):
    return agent.tool_todo_list(args)

