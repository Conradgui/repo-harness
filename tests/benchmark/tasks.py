"""Benchmark 任务定义。"""

TASKS = [
    {
        "id": "BM_001",
        "name": "代码理解 — 解释指定函数",
        "prompt": (
            "Read rich/markdown.py, find the Paragraph.__init__ method (around line 117), "
            "explain what it does and what parameters it accepts."
        ),
        "baseline_prompt": (
            "In the Python library 'rich', the file rich/markdown.py contains a Paragraph class. "
            "Explain what its __init__ method does (around line 117) and what parameters it accepts. "
            "Answer based on your knowledge of the rich library."
        ),
        "check_file": "rich/markdown.py",
        "expected_in_response": ["Paragraph", "justify"],
    },
    {
        "id": "BM_002",
        "name": "代码修改 — 添加 docstring",
        "prompt": (
            "Read rich/markdown.py lines 110-130, find the Paragraph.__init__ method, "
            "and add a one-line docstring explaining it initializes a paragraph element "
            "with a justify parameter."
        ),
        "baseline_prompt": (
            "In the Python library 'rich', the file rich/markdown.py has a Paragraph class "
            "with an __init__ method around line 117 that takes a 'justify' parameter. "
            "Write a one-line docstring for it and explain where to add it."
        ),
        "check_file": "rich/markdown.py",
        "target_line_contains": "def __init__",
    },
    {
        "id": "BM_003",
        "name": "命令执行 — 跑测试并报告",
        "prompt": "Run python -m pytest tests/test_markdown.py -q --tb=short and report the results.",
        "baseline_prompt": (
            "How would you run tests for the markdown module in the Python 'rich' library? "
            "What pytest command would you use and what results would you expect?"
        ),
        "check_file": None,
        "expected_in_response": ["test", "pass"],
    },
    {
        "id": "BM_004",
        "name": "多步骤任务 — 读→改→测",
        "prompt": (
            "1. Read rich/markdown.py lines 110-130.\n"
            "2. Add a one-line docstring to Paragraph.__init__.\n"
            "3. Run python -m pytest tests/test_markdown.py -q to verify tests still pass.\n"
            "Report what you did and the test results."
        ),
        "baseline_prompt": (
            "I need to: 1) Read rich/markdown.py lines 110-130 in the 'rich' library, "
            "2) Add a docstring to Paragraph.__init__, "
            "3) Run pytest tests/test_markdown.py to verify.\n"
            "Write out the complete plan with the docstring text and expected pytest command."
        ),
        "check_file": "rich/markdown.py",
        "target_line_contains": "def __init__",
    },
    {
        "id": "BM_005",
        "name": "错误恢复 — 失败后自动调整",
        "prompt": (
            "Run python -m pytest tests/test_nonexistent.py -q. "
            "If it fails, figure out the correct test file name and run that instead. "
            "Report both attempts."
        ),
        "baseline_prompt": (
            "I tried running 'pytest tests/test_nonexistent.py' in the 'rich' library "
            "and it failed with 'file not found'. "
            "What should I do to find the correct test file and run the markdown tests?"
        ),
        "check_file": None,
        "expected_in_response": ["test_markdown"],
    },
]
