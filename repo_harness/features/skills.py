"""Skill discovery, prompt expansion, and slash workflow execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
SKILL_FILE_CREATION_GUIDE = """When creating RepoHarness skill files at .repo-harness/skills/<name>/SKILL.md or skills/<name>/SKILL.md, use frontmatter:
---
name: audit
description: Audit a file
user_invocable: true
---
Audit $ARGUMENTS for risky changes."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str = ""
    prompt: str = ""
    source: str = "builtin"
    skill_root: str = ""
    when_to_use: str = ""
    context: str = "inline"
    allowed_tools: tuple[str, ...] = ()
    argument_hint: str = ""
    user_invocable: bool = True
    disable_model_invocation: bool = False
    model: str = ""
    paths: tuple[str, ...] = ()
    prompt_fn: Callable[[str], str] | None = None

    @property
    def body(self):
        return self.prompt

    @property
    def path(self):
        return str(Path(self.skill_root) / "SKILL.md") if self.skill_root else ""

    def render(self, arguments=""):
        text = self.prompt_fn(str(arguments)) if self.prompt_fn else self.prompt
        replacements = {
            "$ARGUMENTS": str(arguments),
            "${ARGUMENTS}": str(arguments),
            "${REPO_HARNESS_SKILL_DIR}": self.skill_root,
        }
        if self.argument_hint:
            replacements[f"${{{self.argument_hint}}}"] = str(arguments)
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.strip()

    def metadata(self):
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "path": self.path,
            "when_to_use": self.when_to_use,
            "context": self.context,
            "allowed_tools": list(self.allowed_tools),
            "argument_hint": self.argument_hint,
            "paths": list(self.paths),
            "user_invocable": self.user_invocable,
            "disable_model_invocation": self.disable_model_invocation,
            "model": self.model,
        }


def discover_skills(root, user_home=None, home=None):
    from .skills_bundled import bundled_skills

    root = Path(root)
    home_value = user_home if user_home is not None else home
    if home_value is None:
        try:
            home_path = Path.home()
        except RuntimeError:
            home_path = None
    else:
        home_path = Path(home_value)
    skills = {skill.name: skill for skill in bundled_skills()}
    search_roots = []
    if home_path is not None:
        search_roots.append((home_path / ".repo-harness" / "skills", "user"))
    search_roots.extend([
        (root / "skills", "project"),
        (root / ".repo-harness" / "skills", "project"),
    ])
    for directory, source in search_roots:
        for skill in load_skills_from_dir(directory, source=source):
            skills[skill.name] = skill
    # 兼容 Claude Code Skill 格式：从 ~/.claude/skills/ 发现
    try:
        from .claude_code_skills import discover_claude_code_skills
        for skill in discover_claude_code_skills(user_home=str(home_path) if home_path else None):
            skills.setdefault(skill.name, skill)
    except ImportError:
        pass
    return dict(sorted(skills.items()))


def load_skills_from_dir(skills_dir, source):
    skills_dir = Path(skills_dir).expanduser()
    if not skills_dir.exists():
        return []
    files = []
    for path in sorted(skills_dir.iterdir()):
        if path.is_dir() and (path / "SKILL.md").is_file():
            files.append(path / "SKILL.md")
        elif path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
    return [skill for path in files if (skill := load_skill_file(path, source=source))]


def load_skill_file(path, source):
    path = Path(path)
    metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    default_name = path.parent.name if path.name == "SKILL.md" else path.stem
    name = str(metadata.get("name") or default_name).strip().lstrip("/")
    if not name:
        return None
    default_disable = False if "context" in metadata else True
    return Skill(
        name=name,
        description=_string(metadata.get("description")),
        when_to_use=_string(metadata.get("when_to_use")),
        context=_string(metadata.get("context"), "inline") or "inline",
        allowed_tools=tuple(_list_value(metadata.get("allowed_tools"))),
        argument_hint=_string(metadata.get("arguments") or metadata.get("argument_hint")),
        user_invocable=_bool_value(metadata.get("user_invocable", True)),
        disable_model_invocation=_bool_value(metadata.get("disable_model_invocation", default_disable)),
        model=_string(metadata.get("model")),
        paths=tuple(_list_value(metadata.get("paths"))),
        source=source,
        skill_root=str(path.parent),
        prompt=body.strip(),
    )


def parse_frontmatter(text):
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
        current_key = key.strip().lower().replace("-", "_")
        value = value.strip()
        metadata[current_key] = [] if not value else _parse_value(value)
    return metadata, str(text)[match.end() :]


def render_prompt_section(skills):
    visible = [skill for skill in list_skills(skills, user_invocable_only=False) if _should_show_in_prompt(skill)]
    if not visible:
        return "Available skills:\n- none"
    lines = ["Available skills:"]
    for skill in visible:
        description = skill.description or skill.when_to_use or "No description"
        suffix = f" - {skill.when_to_use}" if skill.when_to_use else ""
        lines.append(f"- /{skill.name}: {description}{suffix}")
    return "\n".join(lines)


def render_skills_list(skills):
    items = list_skills(skills)
    if not items:
        return "Skills:\n- none"
    lines = ["Skills:"]
    for skill in items:
        description = skill.description or skill.when_to_use or "No description"
        hint = f" [{skill.argument_hint}]" if skill.argument_hint else ""
        lines.append(f"- /{skill.name}{hint} {description} [{skill.source}]")
    return "\n".join(lines)


def list_skills(skills, user_invocable_only=True):
    items = [skills[name] for name in sorted(skills)]
    if user_invocable_only:
        items = [skill for skill in items if skill.user_invocable]
    return sorted(items, key=lambda skill: (skill.source != "builtin", skill.name))


def parse_slash_command(text):
    text = str(text).strip()
    if not text.startswith("/") or text == "/":
        return "", ""
    command, _, arguments = text[1:].partition(" ")
    return command.strip(), arguments.strip()


def invoke_skill(skills, name, arguments=""):
    skill = skills.get(str(name).strip().lstrip("/"))
    if skill is None:
        return f"skill not found: {name}"
    return render_skill_prompt(skill, arguments)


def render_skill_prompt(skill, arguments=""):
    return (
        f"Skill: {skill.name}\nSource: {skill.source}\nContext: {skill.context}\n"
        f"Arguments: {arguments}\n\n{skill.render(arguments)}"
    )


def _parse_value(value):
    value = value.strip().strip("\"'")
    if value.lower() in {"true", "yes"}:
        return True
    if value.lower() in {"false", "no"}:
        return False
    if "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _list_value(value):
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _string(value, default=""):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _bool_value(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _should_show_in_prompt(skill):
    return skill.user_invocable or bool(skill.paths)
