"""Tests for Claude Code Skill compatibility adapter."""


from repo_harness.features.claude_code_skills import (
    map_tool_name,
    map_allowed_tools,
    parse_claude_code_frontmatter,
    load_claude_code_skill,
    discover_claude_code_skills,
)


def test_map_tool_name_simple():
    assert map_tool_name("Read") == "read_file"
    assert map_tool_name("Write") == "write_file"
    assert map_tool_name("Edit") == "patch_file"
    assert map_tool_name("Bash") == "run_shell"
    assert map_tool_name("Glob") == "list_files"
    assert map_tool_name("Grep") == "search"


def test_map_tool_name_bash_scoped():
    assert map_tool_name("Bash(python3:*)") == "run_shell"
    assert map_tool_name("Bash(git:*)") == "run_shell"
    assert map_tool_name("Bash(find:*)") == "run_shell"


def test_map_tool_name_unknown():
    assert map_tool_name("UnknownTool") is None
    assert map_tool_name("mcp__notion__search") is None


def test_map_allowed_tools():
    result = map_allowed_tools(["Read", "Write", "Bash(python3:*)", "Grep"])
    assert result == ("read_file", "write_file", "run_shell", "search")


def test_map_allowed_tools_deduplicates():
    result = map_allowed_tools(["Bash", "Bash(python3:*)", "Bash(git:*)"])
    assert result == ("run_shell",)


def test_parse_claude_code_frontmatter():
    text = """---
name: humanizer
description: Remove AI writing patterns
allowed-tools: Read, Write, Edit, Grep
version: 2.7.0
---
Your prompt here.
"""
    metadata, body = parse_claude_code_frontmatter(text)
    assert metadata["name"] == "humanizer"
    assert metadata["description"] == "Remove AI writing patterns"
    assert metadata["allowed_tools"] == ["Read", "Write", "Edit", "Grep"]
    assert metadata["version"] == "2.7.0"
    assert "Your prompt here." in body


def test_parse_claude_code_frontmatter_list_format():
    text = """---
name: apex
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---
Prompt body.
"""
    metadata, body = parse_claude_code_frontmatter(text)
    assert metadata["allowed_tools"] == ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


def test_load_claude_code_skill(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("""---
name: test-skill
description: A test skill
allowed-tools: Read, Write, Bash(python3:*)
---
Do something with $ARGUMENTS.
""", encoding="utf-8")

    skill = load_claude_code_skill(skill_file)
    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.description == "A test skill"
    assert skill.allowed_tools == ("read_file", "write_file", "run_shell")
    assert skill.source == "claude-code"
    assert "$ARGUMENTS" in skill.prompt
    assert skill.context == "inline"
    assert skill.user_invocable is True


def test_load_claude_code_skill_no_frontmatter(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("Just a plain markdown file.", encoding="utf-8")

    skill = load_claude_code_skill(skill_file)
    assert skill is not None
    assert skill.prompt == "Just a plain markdown file."


def test_discover_claude_code_skills(tmp_path):
    # Create mock ~/.claude/skills/ structure
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)

    # Skill as directory with SKILL.md
    skill1_dir = skills_dir / "humanizer"
    skill1_dir.mkdir()
    (skill1_dir / "SKILL.md").write_text("""---
name: humanizer
description: Humanize text
allowed-tools: Read, Write
---
Humanize $ARGUMENTS.
""", encoding="utf-8")

    # Skill as flat .md file
    (skills_dir / "apex.md").write_text("""---
name: apex
description: Engineering lead
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---
Route the task.
""", encoding="utf-8")

    skills = discover_claude_code_skills(user_home=str(tmp_path))
    assert len(skills) == 2
    names = [s.name for s in skills]
    assert "humanizer" in names
    assert "apex" in names

    humanizer = next(s for s in skills if s.name == "humanizer")
    assert humanizer.allowed_tools == ("read_file", "write_file")


def test_discover_claude_code_skills_empty_dir(tmp_path):
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    skills = discover_claude_code_skills(user_home=str(tmp_path))
    assert skills == []


def test_discover_claude_code_skills_no_dir(tmp_path):
    skills = discover_claude_code_skills(user_home=str(tmp_path / "nonexistent"))
    assert skills == []
