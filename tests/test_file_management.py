"""文件管理工具测试

验证功能：multi_edit / move_file / copy_file / delete_file / find_files
"""

import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
