"""REPL 两处命令文档必须同步（finding: /help 渲染缺口）。

真实 REPL 的 /help 渲染走 repl_display.build_help_table；cli.HELP_DETAILS
是非交互 fallback 文本。两处是独立事实源：/memory_pack、/stop、/untrust
历史上都只在 HELP_DETAILS 里出现——命令能执行、单测绿、README 也写了，
但用户在 REPL /help 里看不到，可发现性旅程是断的。

本测试把两个事实源的命令集合绑死：任何一侧新增命令而另一侧漏掉都会红。
"""

import re

from rich.console import Console

from repo_harness.cli import HELP_DETAILS
from repo_harness.repl_display import ReplDisplay

COMMAND_TOKEN = re.compile(r"(?<![\w-])(/[a-z_-]+)")


def _help_details_commands():
    return set(COMMAND_TOKEN.findall(HELP_DETAILS))


def _help_table_commands():
    console = Console(record=True, width=120, force_terminal=False)
    console.print(ReplDisplay.build_help_table())
    return set(COMMAND_TOKEN.findall(console.export_text()))


def test_help_details_and_table_cover_same_commands():
    """两个命令事实源的命令集合必须一致，防止单侧漂移。"""
    details = _help_details_commands()
    table = _help_table_commands()
    assert details == table, (
        f"command docs drifted: only in HELP_DETAILS={sorted(details - table)}, "
        f"only in table={sorted(table - details)}"
    )


def test_runtime_control_commands_visible_in_repl_help():
    """/stop 与 /untrust 必须出现在真实 /help 渲染里（用户可发现性）。"""
    table_text_commands = _help_table_commands()
    assert "/stop" in table_text_commands
    assert "/untrust" in table_text_commands


def test_memory_pack_visible_in_repl_help():
    """/memory_pack 的历史漂移已修复：两个事实源都可见。"""
    assert "/memory_pack" in _help_details_commands()
    assert "/memory_pack" in _help_table_commands()
