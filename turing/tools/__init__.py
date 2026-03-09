"""工具注册与管理 (Tool Registration & Management)

Turing 的工具系统基于 ``@tool`` 装饰器自动注册机制：

- 所有 ``*_tools.py`` 模块在导入时，将其中的 ``@tool`` 装饰函数注册到全局 ``_REGISTRY``。
- Agent 初始化时通过 ``import turing.tools.<module>`` 触发注册，无需手动配置。
- 工具 Schema 自动转换为 Ollama function calling 格式。

工具分类（共 12 个模块，26+ 工具）::

    文件操作   — file_tools.py      → read_file, write_file, edit_file
    命令执行   — command_tools.py   → run_command
    代码搜索   — search_tools.py    → search_code, list_directory
    记忆管理   — memory_tools.py    → memory_read, memory_write, memory_reflect
    外部搜索   — external_tools.py  → rag_search, web_search
    自我演化   — evolution_tools.py → learn_from_ai_tool, gap_analysis
    Git 操作   — git_tools.py       → git_status, git_diff, git_log, git_blame
    项目分析   — project_tools.py   → detect_project, analyze_dependencies
    代码质量   — quality_tools.py   → lint_code, format_code, type_check
    批量重构   — refactor_tools.py  → batch_edit, rename_symbol
    测试运行   — test_tools.py      → run_tests, generate_tests

添加新工具::

    from turing.tools.registry import tool

    @tool(name="my_tool", description="...", parameters={...})
    def my_tool(arg: str) -> dict:
        return {"result": "..."}

参见 :mod:`turing.tools.registry` 了解装饰器与调度细节。
"""
