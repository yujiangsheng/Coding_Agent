"""MCP 多服务器连接管理器

管理多个 MCP 服务器的生命周期，统一处理：
- 从配置文件加载服务器定义
- 连接 / 断开 / 重连
- 工具发现与 Turing 注册表同步
- 工具命名隔离（server_name::tool_name 避免冲突）
"""

from __future__ import annotations

import logging
from typing import Any

from turing.mcp.client import MCPClient, mcp_tool_to_turing_schema

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 服务器连接管理器

    管理多个 MCP 服务器连接，将外部工具动态注册到 Turing 工具注册表。

    Usage::

        manager = MCPManager()
        manager.load_from_config({
            "filesystem": {
                "transport": "stdio",
                "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            },
            "github": {
                "transport": "sse",
                "url": "http://localhost:3000",
                "headers": {"Authorization": "Bearer xxx"},
            },
        })
        manager.connect_all()
        # 此时外部工具已注册到 Turing 全局注册表
        # 调用: execute_tool("mcp::filesystem::read_file", {"path": "/tmp/x"})
    """

    def __init__(self):
        self._servers: dict[str, dict] = {}       # name → server config
        self._clients: dict[str, MCPClient] = {}   # name → connected client
        self._registered_tools: dict[str, str] = {}  # turing_tool_name → server_name
        self._readonly_tools: set[str] = set()      # MCP 只读工具集合

    def load_from_config(self, mcp_config: dict) -> None:
        """从配置字典加载 MCP 服务器定义

        Args:
            mcp_config: {
                "server_name": {
                    "transport": "stdio" | "sse",
                    "command": ["cmd", "arg1"],   # stdio 模式
                    "url": "http://...",           # sse 模式
                    "env": {"KEY": "VAL"},         # 可选环境变量
                    "headers": {"K": "V"},         # sse 可选请求头
                    "enabled": true,               # 是否启用（默认 true）
                    "readonly_tools": ["tool1"],   # 声明为只读的工具
                }
            }
        """
        for name, cfg in mcp_config.items():
            if not cfg.get("enabled", True):
                logger.info("MCP 服务器 [%s] 已禁用，跳过", name)
                continue
            self._servers[name] = cfg

    def connect_all(self) -> dict[str, str]:
        """连接所有已注册的 MCP 服务器

        Returns:
            {"server_name": "ok" | "error: ..."} — 每个服务器的连接状态
        """
        results = {}
        for name, cfg in self._servers.items():
            if name in self._clients:
                results[name] = "already connected"
                continue
            try:
                client = self._connect_server(name, cfg)
                self._clients[name] = client
                # 发现并注册工具
                tool_count = self._discover_and_register(name, client, cfg)
                results[name] = f"ok ({tool_count} tools)"
                logger.info("MCP 服务器 [%s] 连接成功，发现 %d 个工具", name, tool_count)
            except Exception as e:
                results[name] = f"error: {e}"
                logger.warning("MCP 服务器 [%s] 连接失败: %s", name, e)
        return results

    def connect_server(self, name: str) -> str:
        """连接单个 MCP 服务器"""
        if name not in self._servers:
            return f"未找到服务器配置: {name}"
        if name in self._clients:
            return "already connected"
        cfg = self._servers[name]
        try:
            client = self._connect_server(name, cfg)
            self._clients[name] = client
            tool_count = self._discover_and_register(name, client, cfg)
            return f"ok ({tool_count} tools)"
        except Exception as e:
            return f"error: {e}"

    def disconnect_server(self, name: str) -> str:
        """断开单个 MCP 服务器并注销其工具"""
        if name not in self._clients:
            return f"服务器 [{name}] 未连接"
        self._unregister_tools(name)
        try:
            self._clients[name].close()
        except Exception:
            pass
        del self._clients[name]
        return "disconnected"

    def disconnect_all(self) -> None:
        """断开所有 MCP 服务器"""
        for name in list(self._clients.keys()):
            self.disconnect_server(name)

    def _connect_server(self, name: str, cfg: dict) -> MCPClient:
        """根据配置连接 MCP 服务器"""
        transport = cfg.get("transport", "stdio")
        if transport == "stdio":
            command = cfg.get("command", [])
            if not command:
                raise ValueError(f"MCP 服务器 [{name}] stdio 模式缺少 command 配置")
            env = cfg.get("env")
            return MCPClient.from_stdio(command, server_name=name, env=env)
        elif transport == "sse":
            url = cfg.get("url", "")
            if not url:
                raise ValueError(f"MCP 服务器 [{name}] SSE 模式缺少 url 配置")
            headers = cfg.get("headers")
            return MCPClient.from_sse(url, server_name=name, headers=headers)
        else:
            raise ValueError(f"不支持的 MCP 传输类型: {transport}")

    def _discover_and_register(self, server_name: str, client: MCPClient, cfg: dict) -> int:
        """发现 MCP 服务器的工具并注册到 Turing 注册表

        工具命名格式: mcp::{server_name}::{tool_name}
        这样可以避免不同服务器的工具名冲突，同时让 LLM 清楚工具来源。
        """
        from turing.tools.registry import _REGISTRY, ToolDef

        tools = client.list_tools()
        readonly_hints = set(cfg.get("readonly_tools", []))
        count = 0
        for tool_def in tools:
            original_name = tool_def.get("name", "")
            if not original_name:
                continue
            turing_name = f"mcp::{server_name}::{original_name}"
            description = tool_def.get("description", f"MCP 工具 ({server_name})")
            schema = mcp_tool_to_turing_schema(tool_def)

            # 创建调用桥接函数
            _client = client
            _orig_name = original_name

            def make_caller(c, n):
                def caller(**kwargs) -> dict:
                    return c.call_tool(n, kwargs)
                return caller

            td = ToolDef(
                name=turing_name,
                description=f"[MCP:{server_name}] {description}",
                parameters=schema,
                func=make_caller(_client, _orig_name),
            )
            _REGISTRY[turing_name] = td
            self._registered_tools[turing_name] = server_name

            # 标记只读工具
            if original_name in readonly_hints:
                self._readonly_tools.add(turing_name)

            count += 1

        return count

    def _unregister_tools(self, server_name: str) -> None:
        """注销指定服务器的所有工具"""
        from turing.tools.registry import _REGISTRY

        to_remove = [name for name, sn in self._registered_tools.items() if sn == server_name]
        for name in to_remove:
            _REGISTRY.pop(name, None)
            del self._registered_tools[name]
            self._readonly_tools.discard(name)

    def call_mcp_tool(self, turing_tool_name: str, arguments: dict) -> dict:
        """通过 Turing 工具名调用 MCP 工具

        与 execute_tool 不同，这里直接路由到对应的 MCP 服务器，
        不走 Turing 的 inspect.signature 过滤逻辑。
        """
        server_name = self._registered_tools.get(turing_tool_name)
        if not server_name:
            return {"error": f"未找到 MCP 工具: {turing_tool_name}"}
        client = self._clients.get(server_name)
        if not client:
            return {"error": f"MCP 服务器 [{server_name}] 未连接"}
        # 提取原始工具名（去掉 mcp::server:: 前缀）
        original_name = turing_tool_name.split("::", 2)[-1] if "::" in turing_tool_name else turing_tool_name
        return client.call_tool(original_name, arguments)

    def get_status(self) -> dict:
        """获取所有 MCP 服务器状态"""
        status = {}
        for name in self._servers:
            client = self._clients.get(name)
            if client:
                info = client.get_server_info()
                status[name] = {
                    "status": "connected",
                    "server_info": info.get("server_info", {}),
                    "tool_count": info.get("tool_count", 0),
                }
            else:
                status[name] = {"status": "disconnected"}
        return status

    def get_mcp_tool_names(self) -> list[str]:
        """返回所有已注册的 MCP 工具名"""
        return list(self._registered_tools.keys())

    def get_readonly_tools(self) -> set[str]:
        """返回 MCP 只读工具集合（可安全并行执行）"""
        return self._readonly_tools.copy()

    def is_mcp_tool(self, tool_name: str) -> bool:
        """判断工具是否来自 MCP"""
        return tool_name in self._registered_tools

    def health_check(self, auto_reconnect: bool = True) -> dict:
        """检测所有 MCP 服务器连接健康状态，可选自动重连（v3.1）

        Returns:
            {"server_name": {"alive": bool, "reconnected": bool}, ...}
        """
        report = {}
        for name, client in list(self._clients.items()):
            alive = client.ping()
            entry = {"alive": alive, "reconnected": False}
            if not alive and auto_reconnect:
                logger.info("MCP 服务器 [%s] 不可达，尝试重连...", name)
                ok = client.reconnect()
                if ok:
                    entry["alive"] = True
                    entry["reconnected"] = True
                    logger.info("MCP 服务器 [%s] 重连成功", name)
                else:
                    # 尝试完全重建连接
                    cfg = self._servers.get(name)
                    if cfg:
                        self._unregister_tools(name)
                        try:
                            new_client = self._connect_server(name, cfg)
                            self._clients[name] = new_client
                            self._discover_and_register(name, new_client, cfg)
                            entry["alive"] = True
                            entry["reconnected"] = True
                            logger.info("MCP 服务器 [%s] 重建连接成功", name)
                        except Exception as e:
                            logger.warning("MCP 服务器 [%s] 重建失败: %s", name, e)
            report[name] = entry
        return report
