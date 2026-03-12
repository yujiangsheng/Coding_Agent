"""工具注册完整性测试"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class TestToolRegistration:
    """验证所有工具正确注册"""

    @pytest.fixture(autouse=True)
    def setup(self):
        import turing.tools.file_tools
        import turing.tools.command_tools
        import turing.tools.search_tools
        import turing.tools.git_tools
        import turing.tools.test_tools
        import turing.tools.quality_tools
        import turing.tools.project_tools
        import turing.tools.refactor_tools
        import turing.tools.ast_tools
        import turing.tools.memory_tools
        import turing.tools.external_tools
        import turing.tools.evolution_tools
        import turing.tools.metacognition_tools
        import turing.tools.benchmark_tools
        import turing.tools.mcp_tools
        import turing.tools.agent_tools
        import turing.tools.github_tools

    def test_total_tool_count(self):
        from turing.tools.registry import get_all_tools
        tools = get_all_tools()
        assert len(tools) == 80, f"Expected 80 tools, got {len(tools)}"

    def test_new_tools_registered(self):
        from turing.tools.registry import get_all_tools
        names = {t.name for t in get_all_tools()}
        new_tools = {
            "multi_edit", "move_file", "copy_file", "delete_file", "find_files",
            "run_background", "check_background", "stop_background",
        }
        missing = new_tools - names
        assert not missing, f"Missing new tools: {missing}"

    def test_v34_tools_registered(self):
        from turing.tools.registry import get_all_tools
        names = {t.name for t in get_all_tools()}
        v34_tools = {
            "context_budget", "task_plan", "checkpoint_save",
            "checkpoint_restore", "test_coverage", "security_scan",
            "pr_summary",
        }
        missing = v34_tools - names
        assert not missing, f"Missing v3.4 tools: {missing}"

    def test_v35_tools_registered(self):
        from turing.tools.registry import get_all_tools
        names = {t.name for t in get_all_tools()}
        v35_tools = {
            "context_compress", "dependency_graph",
            "auto_fix", "verify_hypothesis",
        }
        missing = v35_tools - names
        assert not missing, f"Missing v3.5 tools: {missing}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
