"""工具注册与管理 (Tool Registration & Management)

Turing 的工具系统基于 ``@tool`` 装饰器自动注册机制：

- 所有 ``*_tools.py`` 模块在导入时，将其中的 ``@tool`` 装饰函数注册到全局 ``_REGISTRY``。
- Agent 初始化时通过 ``import turing.tools.<module>`` 触发注册，无需手动配置。
- 工具 Schema 自动转换为 Ollama function calling 格式。

工具分类（共 19 个模块，82 工具）::

    文件操作   — file_tools.py      → read_file, write_file, edit_file, generate_file, multi_edit, move_file, copy_file, delete_file, find_files
    命令执行   — command_tools.py   → run_command, run_background, check_background, stop_background, auto_fix
    代码搜索   — search_tools.py    → search_code, list_directory, repo_map, smart_context, context_budget, context_compress
    记忆管理   — memory_tools.py    → memory_read, memory_write, memory_reflect
    外部搜索   — external_tools.py  → rag_search, web_search, fetch_url
    自我演化   — evolution_tools.py → learn_from_ai_tool, gap_analysis, competitive_benchmark, verify_hypothesis, ...
    Git 操作   — git_tools.py       → git_status, git_diff, git_log, git_blame, git_add, git_commit, git_branch, git_stash
    项目分析   — project_tools.py   → detect_project, analyze_dependencies
    代码质量   — quality_tools.py   → lint_code, format_code, type_check
    批量重构   — refactor_tools.py  → batch_edit, rename_symbol, impact_analysis
    测试运行   — test_tools.py      → run_tests, generate_tests
    AST 分析   — ast_tools.py       → code_structure, call_graph, complexity_report, dependency_graph
    基准评测   — benchmark_tools.py → run_benchmark, eval_code, benchmark_trend
    MCP 协议   — mcp_tools.py       → mcp_list_servers, mcp_list_tools, mcp_call_tool
    元认知     — metacognition_tools.py → metacognitive_reflect, checkpoint
    任务规划   — agent_tools.py     → task_plan
    GitHub     — github_tools.py    → pr_summary, issue_analyze, security_scan, code_review, changelog

添加新工具::

    from turing.tools.registry import tool

    @tool(name="my_tool", description="...", parameters={...})
    def my_tool(arg: str) -> dict:
        return {"result": "..."}

参见 :mod:`turing.tools.registry` 了解装饰器与调度细节。
"""
