"""Sandbox excluded-command matching."""

import fnmatch


def command_is_excluded(command, excluded_commands):
    command = str(command or "")
    return any(fnmatch.fnmatch(command, str(item)) for item in excluded_commands or ())
