"""Pure prompt-building helpers extracted from RepoHarness.

These functions have no runtime state dependency — they take their inputs
as parameters and return computed values. The runtime keeps thin forward
methods that supply the state and assemble the PromptPrefix dataclass.

This keeps prompt construction testable in isolation: you can verify the
exact prompt text without instantiating a full RepoHarness.
"""

from __future__ import annotations

import hashlib
import json
import textwrap

from .. import skills as skillslib


def filter_available_tools(tools, profile):
    """Return the subset of *tools* visible under *profile*.

    If *profile* is ``None`` all tools are returned (the default profile).
    """
    if profile is None:
        return dict(tools)
    return {name: tool for name, tool in tools.items() if profile.allows(name)}


def compute_tool_signature(tools):
    """Produce a stable SHA-256 hash of the tool registry's schema.

    Used by the runtime to detect when the visible tool set changes and
    the prompt prefix must be rebuilt.
    """
    payload = []
    for name in sorted(tools):
        tool = tools[name]
        payload.append(
            {
                "name": name,
                "schema": tool["schema"],
                "risky": tool["risky"],
                "description": tool["description"],
            }
        )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_prompt_text(available_tools, skills):
    """Assemble the system prompt body from visible tools and skills.

    Returns the raw prompt string (without PromptPrefix metadata). The
    runtime wraps this into a :class:`PromptPrefix` with hash, fingerprint,
    and tool signature.
    """
    tool_lines = []
    for name, tool in available_tools.items():
        fields = ", ".join(f"{key}: {value}" for key, value in tool["schema"].items())
        risk = "approval required" if tool["risky"] else "safe"
        tool_lines.append(f"- {name}: ({fields}) [{risk}] {tool['description']}")
    tool_text = "\n".join(tool_lines)
    examples = "\n".join(
        [
            '<tool>{"name":"list_files","args":{"path":"."}}</tool>',
            '<tool>{"name":"read_file","args":{"path":"README.md","start":1,"end":80}}</tool>',
            '<tool name="write_file" path="binary_search.py"><content>def binary_search(nums, target):\n    return -1\n</content></tool>',
            '<tool name="patch_file" path="binary_search.py"><old_text>return -1</old_text><new_text>return mid</new_text></tool>',
            '<tool>{"name":"run_shell","args":{"command":"uv run --with pytest python -m pytest -q","timeout":20}}</tool>',
            "<final>Done.</final>",
        ]
    )
    skills_text = skillslib.render_skills_list(skills)
    return textwrap.dedent(
        f"""\
        You are RepoHarness, a small local coding agent working inside a local repository.

        Rules:
        - Use tools instead of guessing about the workspace.
        - Return exactly one <tool>...</tool> or one <final>...</final>.
        - Tool calls must look like:
          <tool>{{"name":"tool_name","args":{{...}}}}</tool>
        - For write_file and patch_file with multi-line text, prefer XML style:
          <tool name="write_file" path="file.py"><content>...</content></tool>
        - Final answers must look like:
          <final>your answer</final>
        - Never invent tool results.
        - Keep answers concise and concrete.
        - If the user asks you to create or update a specific file and the path is clear, use write_file or patch_file instead of repeatedly listing files.
        - Before writing tests for existing code, read the implementation first.
        - When writing tests, match the current implementation unless the user explicitly asked you to change the code.
        - New files should be complete and runnable, including obvious imports.
        - Do not repeat the same tool call with the same arguments if it did not help. Choose a different tool or return a final answer.
        - Required tool arguments must not be empty. Do not call read_file, write_file, patch_file, run_shell, or delegate with args={{}}.

        Tools:
        {tool_text}

        {skills_text}

        Valid response examples:
        {examples}
        """
    ).strip()
