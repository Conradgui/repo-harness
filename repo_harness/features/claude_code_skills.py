"""Claude Code Skill compatibility adapter.

Allows RepoHarness to discover and load SKILL.md files from Claude Code's
skill directories (~/.claude/skills/, <project>/.claude/skills/).

Maps Claude Code tool names to RepoHarness equivalents and converts
frontmatter fields to RepoHarness Skill format.
"""

from __future__ import annotations

import re
from pathlib import Path

from .skills import FRONTMATTER_RE, Skill, _list_value, _parse_value, _string

# Claude Code tool name → RepoHarness tool name mapping
TOOL_NAME_MAP = {
    "Read": "read_file",
    "read": "read_file",
    "Write": "write_file",
    "write": "write_file",
    "Edit": "patch_file",
    "edit": "patch_file",
    "Bash": "run_shell",
    "bash": "run_shell",
    "Glob": "list_files",
    "glob": "list_files",
    "Grep": "search",
    "grep": "search",
    "AskUserQuestion": "ask_user",
    "ask_user_question": "ask_user",
}

# Bash scoped pattern: Bash(command:*) → extract command prefix
BASH_SCOPE_RE = re.compile(r"^Bash\(([^:]+):\*\)$", re.IGNORECASE)


def map_tool_name(claude_code_tool: str) -> str | None:
    """Map a Claude Code tool name to RepoHarness tool name.

    Handles:
    - Simple names: "Read" → "read_file"
    - Bash scoped: "Bash(python3:*)" → "run_shell" (scope info lost)
    - Unknown tools: returns None (skip)
    """
    claude_code_tool = claude_code_tool.strip()

    # Handle Bash scoped tools: Bash(python3:*) → run_shell
    bash_match = BASH_SCOPE_RE.match(claude_code_tool)
    if bash_match:
        return "run_shell"

    # Direct mapping
    return TOOL_NAME_MAP.get(claude_code_tool)


def map_allowed_tools(claude_code_tools: list[str]) -> tuple[str, ...]:
    """Map a list of Claude Code allowed-tools to RepoHarness tool names."""
    mapped = []
    for tool in claude_code_tools:
        result = map_tool_name(tool.strip())
        if result and result not in mapped:
            mapped.append(result)
    return tuple(mapped)


def parse_claude_code_frontmatter(text: str) -> tuple[dict, str]:
    """Parse Claude Code SKILL.md frontmatter.

    Claude Code uses the same YAML frontmatter format but with different field names:
    - allowed-tools (hyphen) → allowed_tools (underscore)
    - triggers, tags, version, author, license (ignored by RepoHarness)

    Returns (metadata_dict, body_text).
    """
    match = FRONTMATTER_RE.match(str(text))
    if not match:
        return {}, str(text)

    metadata = {}
    current_key = ""
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-") and current_key:
            metadata.setdefault(current_key, [])
            if isinstance(metadata[current_key], list):
                metadata[current_key].append(_parse_value(stripped[1:].strip()))
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        # Normalize key: lowercase, hyphens → underscores
        current_key = key.strip().lower().replace("-", "_")
        value = value.strip()
        metadata[current_key] = [] if not value else _parse_value(value)

    return metadata, str(text)[match.end():]


def load_claude_code_skill(path: Path, source: str = "claude-code") -> Skill | None:
    """Load a single Claude Code SKILL.md file and convert to RepoHarness Skill."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    metadata, body = parse_claude_code_frontmatter(text)

    default_name = path.parent.name if path.name == "SKILL.md" else path.stem
    name = str(metadata.get("name") or default_name).strip().lstrip("/")
    if not name:
        return None

    # Map Claude Code allowed-tools to RepoHarness tool names
    raw_tools = _list_value(metadata.get("allowed_tools"))
    allowed_tools = map_allowed_tools(raw_tools) if raw_tools else ()

    return Skill(
        name=name,
        description=_string(metadata.get("description")),
        when_to_use="",  # Claude Code doesn't have when_to_use
        context="inline",  # Claude Code skills are always inline
        allowed_tools=allowed_tools,
        argument_hint="ARGUMENTS",  # Claude Code uses {{args}} / $ARGUMENTS
        user_invocable=True,
        disable_model_invocation=False,
        model="",
        paths=(),
        source=source,
        skill_root=str(path.parent),
        prompt=body.strip(),
    )


def discover_claude_code_skills(user_home=None) -> list[Skill]:
    """Discover Claude Code skills from standard directories.

    Searches:
    - ~/.claude/skills/<name>/SKILL.md (user-level)
    - ~/.claude/skills/<name>.md (user-level flat)

    Returns list of discovered skills.
    """
    skills = []

    if user_home is None:
        try:
            user_home = str(Path.home())
        except RuntimeError:
            return skills

    home = Path(user_home)
    claude_skills_dir = home / ".claude" / "skills"

    if not claude_skills_dir.exists():
        return skills

    try:
        for path in sorted(claude_skills_dir.iterdir()):
            if path.is_dir() and (path / "SKILL.md").is_file():
                skill = load_claude_code_skill(path / "SKILL.md")
                if skill:
                    skills.append(skill)
            elif path.is_file() and path.suffix.lower() == ".md":
                skill = load_claude_code_skill(path)
                if skill:
                    skills.append(skill)
    except OSError:
        pass

    return skills
