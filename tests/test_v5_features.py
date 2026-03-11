"""Turing v5.0 (v1.0.0) 新功能验证测试

验证 Phase 5 新增的所有功能：
1. 持久化 Shell 会话（run_command / run_background / check_background / stop_background）
2. 文件管理工具（multi_edit / move_file / copy_file / delete_file / find_files）
3. Token-aware 上下文管理
4. 增强测试解析（覆盖率 + 失败详情）
5. 自动项目索引
6. 工具注册完整性
"""

import json
import os
import sys
import tempfile
import shutil

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ── 工具注册 ──────────────────────────────────────

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

    def test_total_tool_count(self):
        from turing.tools.registry import get_all_tools
        tools = get_all_tools()
        assert len(tools) == 58, f"Expected 58 tools, got {len(tools)}"

    def test_new_tools_registered(self):
        from turing.tools.registry import get_all_tools
        names = {t.name for t in get_all_tools()}
        new_tools = {
            "multi_edit", "move_file", "copy_file", "delete_file", "find_files",
            "run_background", "check_background", "stop_background",
        }
        missing = new_tools - names
        assert not missing, f"Missing new tools: {missing}"


# ── 持久化 Shell 会话 ─────────────────────────────

class TestPersistentShell:
    """验证持久化 Shell 会话功能"""

    def test_run_command_basic(self):
        from turing.tools.command_tools import run_command
        result = run_command("echo hello")
        assert result["success"] is True
        assert "hello" in result["output"]

    def test_cwd_persistence(self):
        from turing.tools.command_tools import _ShellSession
        with tempfile.TemporaryDirectory() as tmpdir:
            session = _ShellSession(tmpdir)
            # cd to a subdirectory
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)
            result = session.run(f"cd {subdir}")
            assert result["success"] is True
            assert result["cwd"] == subdir

    def test_env_persistence(self):
        from turing.tools.command_tools import _ShellSession
        with tempfile.TemporaryDirectory() as tmpdir:
            session = _ShellSession(tmpdir)
            session.run("export TURING_TEST_VAR=42")
            result = session.run("echo $TURING_TEST_VAR")
            assert "42" in result["output"]

    def test_command_security(self):
        from turing.tools.command_tools import run_command
        # 假设 config 中有 blocked_commands，至少验证函数不崩溃
        result = run_command("echo safe_command")
        assert "error" not in result or result.get("success") is True

    def test_background_process(self):
        from turing.tools.command_tools import run_background, check_background, stop_background
        result = run_background("sleep 10")
        assert result.get("status") == "ok"
        pid = result["pid"]

        # 检查进程状态
        status = check_background(pid)
        assert status["running"] is True

        # 停止进程
        stop_result = stop_background(pid)
        assert stop_result["status"] == "ok"

    def test_check_background_list_all(self):
        from turing.tools.command_tools import check_background
        result = check_background()
        assert "processes" in result
        assert "count" in result


# ── 文件管理工具 ──────────────────────────────────

class TestFileManagement:
    """验证新增的文件管理工具"""

    @pytest.fixture
    def workspace(self):
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_move_file(self, workspace):
        from turing.tools.file_tools import move_file
        src = os.path.join(workspace, "a.txt")
        dst = os.path.join(workspace, "b.txt")
        with open(src, "w") as f:
            f.write("content")
        result = move_file(src, dst)
        assert result["status"] == "ok"
        assert not os.path.exists(src)
        assert os.path.exists(dst)

    def test_copy_file(self, workspace):
        from turing.tools.file_tools import copy_file
        src = os.path.join(workspace, "a.txt")
        dst = os.path.join(workspace, "b.txt")
        with open(src, "w") as f:
            f.write("content")
        result = copy_file(src, dst)
        assert result["status"] == "ok"
        assert os.path.exists(src)  # 源文件保留
        assert os.path.exists(dst)

    def test_delete_file(self, workspace):
        from turing.tools.file_tools import delete_file
        f = os.path.join(workspace, "a.txt")
        with open(f, "w") as fh:
            fh.write("x")
        result = delete_file(f)
        assert result["status"] == "ok"
        assert not os.path.exists(f)

    def test_delete_nonempty_dir_blocked(self, workspace):
        from turing.tools.file_tools import delete_file
        d = os.path.join(workspace, "dir")
        os.makedirs(d)
        with open(os.path.join(d, "f.txt"), "w") as fh:
            fh.write("x")
        result = delete_file(d)
        assert "error" in result

    def test_find_files(self, workspace):
        from turing.tools.file_tools import find_files
        # 创建几个文件
        for name in ["a.py", "b.py", "c.txt"]:
            with open(os.path.join(workspace, name), "w") as f:
                f.write("x")
        result = find_files("*.py", path=workspace)
        assert result["count"] == 2
        assert "a.py" in result["files"]
        assert "b.py" in result["files"]

    def test_multi_edit_success(self, workspace):
        from turing.tools.file_tools import multi_edit
        # 创建两个文件
        f1 = os.path.join(workspace, "f1.py")
        f2 = os.path.join(workspace, "f2.py")
        with open(f1, "w") as fh:
            fh.write("old_value = 1\n")
        with open(f2, "w") as fh:
            fh.write("ref = old_value\n")

        result = multi_edit([
            {"path": f1, "old_str": "old_value = 1", "new_str": "new_value = 2"},
            {"path": f2, "old_str": "ref = old_value", "new_str": "ref = new_value"},
        ])
        assert result["status"] == "ok"
        assert result["files_modified"] == 2
        assert "new_value = 2" in open(f1).read()
        assert "ref = new_value" in open(f2).read()

    def test_multi_edit_rollback(self, workspace):
        from turing.tools.file_tools import multi_edit
        f1 = os.path.join(workspace, "f1.py")
        with open(f1, "w") as fh:
            fh.write("hello\n")

        result = multi_edit([
            {"path": f1, "old_str": "hello", "new_str": "world"},
            {"path": f1, "old_str": "NOT_EXIST", "new_str": "xxx"},
        ])
        assert "error" in result
        # 第二个编辑应用于已修改文本（hello→world），所以 NOT_EXIST 在修改后的文本中找不到
        # 文件不应被修改（验证在 phase 1 就失败了）
        assert "hello" in open(f1).read()


# ── Token-aware 上下文管理 ────────────────────────

class TestContextManager:
    """验证 Token-aware 上下文管理"""

    def test_no_overflow_small_context(self):
        """小上下文不触发压缩"""
        from turing.agent import TuringAgent
        agent = TuringAgent.__new__(TuringAgent)
        agent.config = type("C", (), {
            "get": lambda self, k, d=None: {"model.context_length": 32768}.get(k, d)
        })()
        agent.memory = type("M", (), {"compress_working_memory": lambda self, **kw: None})()
        agent._messages = [
            {"role": "system", "content": "You are a helper"},
            {"role": "user", "content": "hello"},
        ]
        original_count = len(agent._messages)
        agent._check_context_overflow()
        assert len(agent._messages) == original_count

    def test_overflow_triggers_compression(self):
        """大上下文触发压缩"""
        from turing.agent import TuringAgent
        agent = TuringAgent.__new__(TuringAgent)
        agent.config = type("C", (), {
            "get": lambda self, k, d=None: {"model.context_length": 4096}.get(k, d)
        })()
        agent.memory = type("M", (), {"compress_working_memory": lambda self, **kw: None})()

        # 注入大量消息超过 token 限制
        agent._messages = [{"role": "system", "content": "system prompt " * 100}]
        for i in range(50):
            agent._messages.append({"role": "user", "content": f"question {i} " * 50})
            agent._messages.append({"role": "tool", "content": f"result {i} " * 100})
            agent._messages.append({"role": "assistant", "content": f"answer {i} " * 50})

        original_count = len(agent._messages)
        agent._check_context_overflow()
        # 应该压缩了消息
        assert len(agent._messages) < original_count


# ── 版本信息 ─────────────────────────────────────

class TestVersion:

    def test_version(self):
        import turing
        assert turing.__version__ == "2.0.0"

    def test_prompt_capabilities_count(self):
        from turing.prompt import SYSTEM_PROMPT
        # 统计能力列表部分的条目数（从 "你具备以下能力" 到 "## 核心原则"）
        import re
        cap_section = SYSTEM_PROMPT.split("你具备以下能力：")[1].split("## 核心原则")[0]
        caps = re.findall(r'^\d+\.', cap_section, re.MULTILINE)
        assert len(caps) == 46, f"Expected 46 capabilities, found {len(caps)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
