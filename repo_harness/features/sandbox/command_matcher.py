"""Sandbox excluded-command matching."""

import shlex


def command_is_excluded(command, excluded_commands):
    try:
        head = shlex.split(str(command), posix=False)[0]
    except Exception:
        head = str(command).strip().split(maxsplit=1)[0] if str(command).strip() else ""
    head = head.lower()
    return any(head == str(item).lower() for item in excluded_commands or ())

