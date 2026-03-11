"""记忆系统工具

提供三个记忆操作原语，作为 MemoryManager 的工具层接口：
- memory_read    — 从指定层检索记忆
- memory_write   — 向指定层写入记忆
- memory_reflect — 触发任务反思，归纳总结后存入长期记忆

全局 MemoryManager 实例在 Agent 启动时通过 ``set_memory_manager()`` 注入。
"""

from __future__ import annotations
from typing import Any

from turing.tools.registry import tool

# 全局引用，agent 启动时注入
_memory_manager = None


def set_memory_manager(mm):
    """注入全局 MemoryManager 实例（Agent 启动时调用）。"""
    global _memory_manager
    _memory_manager = mm


def _get_mm():
    """获取全局 MemoryManager 实例。"""
    if _memory_manager is None:
        return None
    return _memory_manager


@tool(
    name="memory_read",
    description="从记忆系统中检索信息。可指定层：working（工作记忆）、long_term（长期记忆）、persistent（持久记忆）。",
    parameters={
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "description": "记忆层: working / long_term / persistent",
                "enum": ["working", "long_term", "persistent"],
            },
            "query": {"type": "string", "description": "检索关键词"},
            "top_k": {
                "type": "integer",
                "description": "返回条数，默认5",
            },
        },
        "required": ["layer", "query"],
    },
)
def memory_read(layer: str, query: str, top_k: int = 5) -> dict:
    """从指定层检索记忆。"""
    mm = _get_mm()
    if mm is None:
        return {"error": "记忆系统未初始化"}
    results = mm.retrieve(query, [layer], top_k)
    return {"results": results, "count": len(results)}


@tool(
    name="memory_write",
    description="向记忆系统写入信息。layer: working（工作记忆）、long_term（长期记忆）、persistent（持久记忆）。",
    parameters={
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "description": "记忆层: working / long_term / persistent",
                "enum": ["working", "long_term", "persistent"],
            },
            "content": {"type": "string", "description": "要存储的内容"},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表（可选）",
            },
        },
        "required": ["layer", "content"],
    },
)
def memory_write(layer: str, content: str, tags: list[str] = None) -> dict:
    """向指定层写入记忆。"""
    mm = _get_mm()
    if mm is None:
        return {"error": "记忆系统未初始化"}
    return mm.write(layer, content, tags)


@tool(
    name="memory_reflect",
    description="触发自我反思：将当前任务经验归纳总结后存入长期记忆。任务完成后应调用此工具。",
    parameters={
        "type": "object",
        "properties": {
            "task_summary": {"type": "string", "description": "任务摘要"},
            "outcome": {
                "type": "string",
                "description": "任务结果: success / failure / partial",
                "enum": ["success", "failure", "partial"],
            },
            "lessons": {"type": "string", "description": "经验教训"},
        },
        "required": ["task_summary", "outcome", "lessons"],
    },
)
def memory_reflect(task_summary: str, outcome: str, lessons: str) -> dict:
    """触发任务反思，归纳经验并存入长期记忆。"""
    mm = _get_mm()
    if mm is None:
        return {"error": "记忆系统未初始化"}
    return mm.reflect(task_summary, outcome, lessons)
