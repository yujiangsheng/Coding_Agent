"""演化学习工具

提供 learn_from_ai_tool 工具，用于分析 Claude Opus / Codex / Gemini /
Copilot 等顶尖 AI 编程工具的策略，提取可学习的模式并内化。

全局 EvolutionTracker 实例在 Agent 启动时通过 ``set_evolution_tracker()`` 注入。
"""

from __future__ import annotations

from turing.tools.registry import tool

_evolution_tracker = None


def set_evolution_tracker(tracker):
    global _evolution_tracker
    _evolution_tracker = tracker


@tool(
    name="learn_from_ai_tool",
    description="分析顶尖 AI 编程工具的策略，提取可学习的模式和技巧。",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "AI 工具名称",
                "enum": ["claude_opus", "codex", "gemini", "copilot"],
            },
            "task_type": {
                "type": "string",
                "description": "任务类型（如 bug_fix, feature, refactor）",
            },
            "reference_output": {
                "type": "string",
                "description": "该工具的参考输出（可选）",
            },
        },
        "required": ["tool_name", "task_type"],
    },
)
def learn_from_ai_tool(tool_name: str, task_type: str, reference_output: str = None) -> dict:
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.learn_from(tool_name, task_type, reference_output)


@tool(
    name="gap_analysis",
    description="分析 Turing 与 Claude Opus / Codex / Gemini / Copilot 等顶尖 AI 编码工具的能力差距，生成详细的差距报告和改进路线图。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def gap_analysis() -> dict:
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.analyze_gaps()
