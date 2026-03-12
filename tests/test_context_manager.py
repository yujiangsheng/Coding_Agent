"""Token-aware 上下文管理测试"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
