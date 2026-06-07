"""Compatibility entrypoint for RepoHarness skills."""

from .features.skills import (
    Skill,
    discover_skills,
    invoke_skill,
    list_skills,
    parse_slash_command,
    render_prompt_section,
    render_skill_prompt,
    render_skills_list,
)
