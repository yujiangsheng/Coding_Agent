"""持久化 Shell 会话测试

验证功能：run_command / run_background / check_background / stop_background
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
