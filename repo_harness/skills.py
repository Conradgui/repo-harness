"""RepoHarness skill discovery and invocation."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: str
    when_to_use: str = ""
    context: str = "inline"
    allowed_tools: tuple = ()
    argument_hint: str = ""
    user_invocable: bool = True
    disable_model_invocation: bool = True
    model: str = ""
    paths: tuple = ()

    def metadata(self):
        return {
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "when_to_use": self.when_to_use,
            "context": self.context,
            "allowed_tools": list(self.allowed_tools),
            "argument_hint": self.argument_hint,
            "user_invocable": self.user_invocable,
            "disable_model_invocation": self.disable_model_invocation,
            "model": self.model,
            "paths": list(self.paths),
        }


def _split_list(value):
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(item.strip() for item in str(value or "").split(",") if item.strip())


def _bool_value(value, default=True):
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _parse_skill(path):
    text = Path(path).read_text(encoding="utf-8")
    name = Path(path).parent.name
    description = ""
    body = text
    metadata = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            frontmatter = parts[1]
            body = parts[2].strip()
            for line in frontmatter.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip().strip("\"'")
                metadata[key] = value
                if key == "name" and value:
                    name = value
                if key == "description":
                    description = value
    default_disable = False if "context" in metadata else True
    return Skill(
        name=name,
        description=description,
        body=body.strip(),
        path=str(path),
        when_to_use=str(metadata.get("when_to_use", "")).strip(),
        context=str(metadata.get("context", "inline")).strip() or "inline",
        allowed_tools=_split_list(metadata.get("allowed_tools", "")),
        argument_hint=str(metadata.get("arguments", metadata.get("argument_hint", ""))).strip(),
        user_invocable=_bool_value(metadata.get("user_invocable", "true"), default=True),
        disable_model_invocation=_bool_value(metadata.get("disable_model_invocation", ""), default=default_disable),
        model=str(metadata.get("model", "")).strip(),
        paths=_split_list(metadata.get("paths", "")),
    )


def discover_skills(root, user_home=None):
    root = Path(root)
    candidates = [
        root / "skills",
        root / ".repo-harness" / "skills",
    ]
    if user_home:
        candidates.append(Path(user_home) / ".repo-harness" / "skills")
    skills = {}
    for directory in candidates:
        if not directory.is_dir():
            continue
        for skill_path in sorted(directory.glob("*/SKILL.md")):
            skill = _parse_skill(skill_path)
            skills[skill.name] = skill
    return skills


def render_skills_list(skills):
    if not skills:
        return "Skills:\n- none"
    lines = ["Skills:"]
    for name in sorted(skills):
        skill = skills[name]
        suffix = f" - {skill.description}" if skill.description else ""
        lines.append(f"- {name}{suffix}")
    return "\n".join(lines)


def render_skill_prompt(skill, arguments=""):
    arguments = str(arguments).strip()
    body = skill.body
    replacements = {
        "$ARGUMENTS": arguments,
        "${ARGUMENTS}": arguments,
        "${REPO_HARNESS_SKILL_DIR}": str(Path(skill.path).parent),
    }
    if skill.argument_hint:
        replacements[f"${{{skill.argument_hint}}}"] = arguments
    for token, value in replacements.items():
        body = body.replace(token, value)
    lines = [f"Skill: {skill.name}"]
    if skill.description:
        lines.append(f"Description: {skill.description}")
    if arguments:
        lines.append(f"Arguments: {arguments}")
    lines.append(body)
    return "\n".join(lines)


def invoke_skill(skills, name, arguments=""):
    skill = skills.get(str(name).strip())
    if skill is None:
        return f"skill not found: {name}"
    return render_skill_prompt(skill, arguments)
