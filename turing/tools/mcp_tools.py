"""MCP 管理工具

提供 3 个工具用于管理 MCP 服务器连接和外部工具调用：
- mcp_list_servers — 列出已配置/已连接的 MCP 服务器状态
- mcp_list_tools — 列出 MCP 服务器提供的工具
- mcp_call_tool — 调用 MCP 服务器提供的工具
"""

from __future__ import annotations

from typing import Any

from turing.tools.registry import tool

# 运行时注入 MCPManager 实例
_mcp_manager = None


def set_mcp_manager(manager) -> None:
    """注入 MCPManager 实例（由 TuringAgent.__init__ 调用）"""
    global _mcp_manager
    _mcp_manager = manager


@tool(
    name="mcp_list_servers",
    description="列出所有已配置的 MCP 服务器及其连接状态、工具数量",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def mcp_list_servers() -> dict:
    """列出 MCP 服务器状态"""
    if _mcp_manager is None:
        return {"error": "MCP 未初始化（config.yaml 中未配置 mcp.servers）"}
    status = _mcp_manager.get_status()
    if not status:
        return {"servers": [], "message": "未配置任何 MCP 服务器"}
    servers = []
    for name, info in status.items():
        servers.append({
            "name": name,
            "status": info.get("status", "unknown"),
            "tool_count": info.get("tool_count", 0),
            "server_info": info.get("server_info", {}),
        })
    return {"servers": servers, "total": len(servers)}


@tool(
    name="mcp_list_tools",
    description="列出指定 MCP 服务器提供的工具列表。不指定服务器则列出全部 MCP 工具",
    parameters={
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "description": "MCP 服务器名称（可选，不指定则列出全部）",
            },
        },
        "required": [],
    },
)
def mcp_list_tools(server: str = "") -> dict:
    """列出 MCP 工具"""
    if _mcp_manager is None:
        return {"error": "MCP 未初始化"}
    all_tools = _mcp_manager.get_mcp_tool_names()
    if server:
        tools = [t for t in all_tools if t.startswith(f"mcp::{server}::")]
    else:
        tools = all_tools
    # 格式化输出
    tool_list = []
    for name in tools:
        parts = name.split("::", 2)
        tool_list.append({
            "turing_name": name,
            "server": parts[1] if len(parts) > 1 else "?",
            "tool": parts[2] if len(parts) > 2 else name,
        })
    return {"tools": tool_list, "total": len(tool_list)}


@tool(
    name="mcp_call_tool",
    description="调用 MCP 服务器提供的外部工具。使用完整的 Turing 工具名（格式: mcp::server::tool）",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "MCP 工具的完整名称（格式: mcp::server::tool_name）",
            },
            "arguments": {
                "type": "object",
                "description": "传给工具的参数字典",
            },
        },
        "required": ["tool_name"],
    },
)
def mcp_call_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict:
    """调用 MCP 工具"""
    if _mcp_manager is None:
        return {"error": "MCP 未初始化"}
    if not tool_name.startswith("mcp::"):
        return {"error": f"无效的 MCP 工具名（应以 mcp:: 开头）: {tool_name}"}
    return _mcp_manager.call_mcp_tool(tool_name, arguments or {})
