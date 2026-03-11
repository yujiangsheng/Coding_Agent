"""工具注册表

共四个职责：
1. 定义 ToolDef 数据类，封装工具的名称、描述、参数 Schema 和实现函数
2. 提供 @tool 装饰器，自动注册工具到全局注册表 _REGISTRY
3. 生成 Ollama function calling 格式的 Schema
4. 安全调度执行：自动过滤无关参数，捕获异常

Usage::

    @tool(
        name="my_tool",
        description="做某件事",
        parameters={"type": "object", "properties": {...}, "required": [...]},
    )
    def my_tool(arg1: str) -> dict:
        return {"result": "..."}
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

# 全局工具注册表 {name: ToolDef}
_REGISTRY: dict[str, "ToolDef"] = {}


class ToolDef:
    """一个已注册的工具"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,  # JSON-Schema 格式
        func: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_ollama_schema(self) -> dict:
        """转换为 Ollama function calling 的 schema 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool(
    name: str,
    description: str,
    parameters: dict,
):
    """工具注册装饰器

    @tool(
        name="read_file",
        description="读取文件内容",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"],
        },
    )
    def read_file(path: str) -> dict: ...
    """

    def decorator(func: Callable) -> Callable:
        td = ToolDef(name=name, description=description, parameters=parameters, func=func)
        _REGISTRY[name] = td
        return func

    return decorator


def get_all_tools() -> list[ToolDef]:
    """返回所有已注册的工具"""
    return list(_REGISTRY.values())


def get_tool(name: str) -> ToolDef | None:
    """按名称查找已注册的工具，未找到返回 None。"""
    return _REGISTRY.get(name)


def get_ollama_tool_schemas() -> list[dict]:
    """生成供 Ollama function calling 使用的工具 schema 列表"""
    return [td.to_ollama_schema() for td in _REGISTRY.values()]


def execute_tool(name: str, arguments: dict) -> dict:
    """执行指定工具，返回结果 dict"""
    td = _REGISTRY.get(name)
    if td is None:
        return {"error": f"未知工具: {name}"}
    try:
        # 只传入函数签名中接受的参数
        sig = inspect.signature(td.func)
        valid_args = {k: v for k, v in arguments.items() if k in sig.parameters}
        result = td.func(**valid_args)
        if not isinstance(result, dict):
            result = {"result": result}
        return result
    except Exception as e:
        return {"error": f"工具 {name} 执行失败: {e}"}
