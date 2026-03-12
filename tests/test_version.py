"""版本信息与 Prompt 能力验证测试"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class TestVersion:

    def test_version(self):
        import turing
        assert turing.__version__ == "3.5.0"

    def test_prompt_capabilities_count(self):
        from turing.prompt import SYSTEM_PROMPT
        # 统计能力列表部分的条目数（从 "你具备以下能力" 到 "## 核心原则"）
        cap_section = SYSTEM_PROMPT.split("你具备以下能力：")[1].split("## 核心原则")[0]
        caps = re.findall(r'^\d+\.', cap_section, re.MULTILINE)
        assert len(caps) == 28, f"Expected 28 capabilities, found {len(caps)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
