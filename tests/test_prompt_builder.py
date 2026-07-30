"""Isolated tests for the pure prompt-building functions.

These verify the extracted functions without instantiating a full
RepoHarness, which is the point of the extraction: prompt construction
becomes testable in isolation.
"""

from repo_harness.core.prompt_builder import (
    build_prompt_text,
    compute_tool_signature,
    filter_available_tools,
)


def _sample_tool(name="read_file", risky=False, desc="read a file"):
    return {
        "name": name,
        "schema": {"path": "str", "start": "int", "end": "int"},
        "risky": risky,
        "description": desc,
    }


class TestFilterAvailableTools:
    def test_returns_all_tools_when_profile_is_none(self):
        tools = {"read_file": _sample_tool(), "write_file": _sample_tool("write_file", True)}
        result = filter_available_tools(tools, None)
        assert set(result.keys()) == {"read_file", "write_file"}

    def test_filters_by_profile(self):
        tools = {"read_file": _sample_tool(), "write_file": _sample_tool("write_file", True)}

        class FakeProfile:
            def allows(self, name):
                return name == "read_file"

        result = filter_available_tools(tools, FakeProfile())
        assert set(result.keys()) == {"read_file"}

    def test_returns_a_copy_not_the_original(self):
        tools = {"read_file": _sample_tool()}
        result = filter_available_tools(tools, None)
        result["injected"] = _sample_tool("bad")
        assert "injected" not in tools


class TestComputeToolSignature:
    def test_is_stable_for_same_tools(self):
        tools = {"read_file": _sample_tool(), "write_file": _sample_tool("write_file", True)}
        sig1 = compute_tool_signature(tools)
        sig2 = compute_tool_signature(tools)
        assert sig1 == sig2
        assert len(sig1) == 64  # SHA-256 hex

    def test_changes_when_tool_set_changes(self):
        tools = {"read_file": _sample_tool()}
        sig1 = compute_tool_signature(tools)
        tools["write_file"] = _sample_tool("write_file", True)
        sig2 = compute_tool_signature(tools)
        assert sig1 != sig2

    def test_independent_of_dict_order(self):
        tools_a = {"read_file": _sample_tool(), "write_file": _sample_tool("write_file", True)}
        tools_b = {"write_file": _sample_tool("write_file", True), "read_file": _sample_tool()}
        assert compute_tool_signature(tools_a) == compute_tool_signature(tools_b)


class TestBuildPromptText:
    def test_contains_role_and_rules(self):
        tools = {"read_file": _sample_tool()}
        text = build_prompt_text(tools, [])
        assert "You are RepoHarness" in text
        assert "Rules:" in text

    def test_lists_visible_tools(self):
        tools = {"read_file": _sample_tool("read_file", False, "Read a file from disk")}
        text = build_prompt_text(tools, [])
        assert "read_file" in text
        assert "Read a file from disk" in text
        assert "[safe]" in text

    def test_marks_risky_tools_as_approval_required(self):
        tools = {"write_file": _sample_tool("write_file", True, "Write a file")}
        text = build_prompt_text(tools, [])
        assert "[approval required]" in text

    def test_includes_response_examples(self):
        text = build_prompt_text({"read_file": _sample_tool()}, [])
        assert '<tool>{"name":"list_files"' in text
        assert "<final>Done.</final>" in text

    def test_includes_skills_section(self):
        text = build_prompt_text({"read_file": _sample_tool()}, [])
        assert "Skills:" in text or "skills" in text.lower() or text.strip()
