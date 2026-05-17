"""RepoHarness skill discovery and invocation."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: str

    def metadata(self):
        return {"name": self.name, "description": self.description, "path": self.path}


def _parse_skill(path):
    text = Path(path).read_text(encoding="utf-8")
    name = Path(path).parent.name
    description = ""
    body = text
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
                if key == "name" and value:
                    name = value
                if key == "description":
                    description = value
    return Skill(name=name, description=description, body=body.strip(), path=str(path))


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


def invoke_skill(skills, name, arguments=""):
    skill = skills.get(str(name).strip())
    if skill is None:
        return f"skill not found: {name}"
    lines = [f"Skill: {skill.name}"]
    if skill.description:
        lines.append(f"Description: {skill.description}")
    if str(arguments).strip():
        lines.append(f"Arguments: {str(arguments).strip()}")
    lines.append(skill.body)
    return "\n".join(lines)
