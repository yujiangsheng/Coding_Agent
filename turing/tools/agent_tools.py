"""子 Agent 分派工具（对标 Claude Code sub-agent / Devin 多 Agent 协作）

将 spawn_sub_agent() 暴露为可被 LLM 自主调用的工具，使 Agent 可以：
- 将复杂任务分解后的子步骤委派给独立子 Agent
- 限制子 Agent 可用的工具集合
- 设置独立的迭代上限

依赖注入模式与 benchmark_tools / memory_tools 相同。
"""

from __future__ import annotations

from typing import Any

from turing.tools.registry import tool

# 全局引用，由 agent.py 初始化时注入
_agent_instance: Any = None


def set_agent_instance(agent) -> None:
    """注入 TuringAgent 实例（由 agent.py __init__ 调用）"""
    global _agent_instance
    _agent_instance = agent


@tool(
    name="delegate_task",
    description=(
        "将子任务委派给独立的子 Agent 执行。子 Agent 拥有独立的消息历史和迭代限制，"
        "共享主 Agent 的配置、记忆和 LLM。适用于：将复杂任务分解后的独立子步骤、"
        "需要隔离上下文的操作、并行可执行的子任务。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "sub_task": {
                "type": "string",
                "description": "子任务描述（会作为用户消息发送给子 Agent）",
            },
            "tools_subset": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限制子 Agent 可用的工具名称列表（可选，默认全部工具）",
            },
            "max_iterations": {
                "type": "integer",
                "description": "子 Agent 最大迭代次数（默认 15）",
            },
        },
        "required": ["sub_task"],
    },
)
def delegate_task(
    sub_task: str,
    tools_subset: list[str] | None = None,
    max_iterations: int = 15,
) -> dict:
    """委派子任务到子 Agent"""
    if _agent_instance is None:
        return {"error": "Agent 实例未初始化，无法分派子任务"}

    return _agent_instance.spawn_sub_agent(
        sub_task=sub_task,
        tools_subset=tools_subset,
        max_iterations=max_iterations,
    )
