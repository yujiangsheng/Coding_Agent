"""MCP（Model Context Protocol）集成模块

实现 MCP 客户端和服务端，让 Turing 既能：
- **作为 MCP Client** — 连接外部 MCP 服务器，动态发现并调用其工具
- **作为 MCP Server** — 将 Turing 的 60+ 工具暴露给外部 MCP 客户端

模块结构::

    mcp/
    ├── __init__.py    — 包入口
    ├── client.py      — MCP 客户端（stdio/SSE 传输，工具发现与调用）
    ├── server.py      — MCP 服务端（暴露 Turing 工具给外部客户端）
    └── manager.py     — 多服务器连接管理器（生命周期管理）
"""

from turing.mcp.client import MCPClient
from turing.mcp.manager import MCPManager

__all__ = ["MCPClient", "MCPManager"]
