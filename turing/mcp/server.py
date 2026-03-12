"""MCP 服务端

将 Turing 的全部工具通过 MCP 协议暴露给外部客户端（Claude Code、VS Code 等）。

支持 stdio 传输模式（标准 MCP 服务器协议）：
- 通过 stdin 读取 JSON-RPC 请求
- 通过 stdout 写入 JSON-RPC 响应
- 实现 initialize、tools/list、tools/call、resources/list 等方法

启动方式::

    python -m turing.mcp.server
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

# Turing 工具注册表
_tools_imported = False


def _ensure_tools_imported():
    """确保所有 Turing 工具已注册"""
    global _tools_imported
    if _tools_imported:
        return
    import turing.tools.file_tools       # noqa: F401
    import turing.tools.command_tools    # noqa: F401
    import turing.tools.search_tools     # noqa: F401
    import turing.tools.memory_tools     # noqa: F401
    import turing.tools.external_tools   # noqa: F401
    import turing.tools.evolution_tools  # noqa: F401
    import turing.tools.git_tools        # noqa: F401
    import turing.tools.test_tools       # noqa: F401
    import turing.tools.quality_tools    # noqa: F401
    import turing.tools.project_tools    # noqa: F401
    import turing.tools.refactor_tools   # noqa: F401
    import turing.tools.ast_tools        # noqa: F401
    import turing.tools.metacognition_tools  # noqa: F401
    import turing.tools.benchmark_tools  # noqa: F401
    _tools_imported = True


class MCPServer:
    """Turing MCP 服务端

    通过 JSON-RPC 2.0 over stdio 暴露 Turing 工具。
    外部 MCP 客户端（Claude Code、Cursor、VS Code 等）可以连接并使用 Turing 的全部工具能力。
    """

    SERVER_INFO = {
        "name": "turing-agent",
        "version": "3.5.0",
    }

    CAPABILITIES = {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
    }

    def __init__(self):
        _ensure_tools_imported()
        self._running = False

    def run(self) -> None:
        """主循环：从 stdin 读取请求，处理后写入 stdout"""
        self._running = True
        logger.info("Turing MCP Server 启动")
        try:
            while self._running:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self._send_error(None, -32700, "Parse error")
                    continue
                self._handle_request(request)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Turing MCP Server 停止")

    def _handle_request(self, request: dict) -> None:
        """分发 JSON-RPC 请求"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        # 通知（无 id）不需要响应
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("MCP 客户端已初始化")
            return

        handler = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "ping": self._handle_ping,
        }.get(method)

        if handler:
            try:
                result = handler(params)
                self._send_result(req_id, result)
            except Exception as e:
                self._send_error(req_id, -32603, f"Internal error: {e}")
        else:
            self._send_error(req_id, -32601, f"Method not found: {method}")

    def _handle_initialize(self, params: dict) -> dict:
        """处理 initialize 请求"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": self.CAPABILITIES,
            "serverInfo": self.SERVER_INFO,
        }

    def _handle_tools_list(self, params: dict) -> dict:
        """处理 tools/list — 返回 Turing 全部工具"""
        from turing.tools.registry import get_all_tools

        tools = []
        for td in get_all_tools():
            # 跳过 MCP 代理工具（避免递归暴露）
            if td.name.startswith("mcp::") or td.name.startswith("mcp_"):
                continue
            tools.append({
                "name": td.name,
                "description": td.description,
                "inputSchema": td.parameters,
            })
        return {"tools": tools}

    def _handle_tools_call(self, params: dict) -> dict:
        """处理 tools/call — 执行指定工具"""
        from turing.tools.registry import execute_tool

        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if not tool_name:
            return {
                "content": [{"type": "text", "text": "缺少工具名称"}],
                "isError": True,
            }

        # 安全检查：不允许通过 MCP 调用 MCP 代理工具
        if tool_name.startswith("mcp::") or tool_name.startswith("mcp_"):
            return {
                "content": [{"type": "text", "text": f"不允许通过 MCP 调用 MCP 工具: {tool_name}"}],
                "isError": True,
            }

        result = execute_tool(tool_name, arguments)

        # 转换为 MCP 结果格式
        is_error = "error" in result
        text = json.dumps(result, ensure_ascii=False, default=str)
        return {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }

    def _handle_resources_list(self, params: dict) -> dict:
        """处理 resources/list — 暴露 Turing 数据目录"""
        return {
            "resources": [
                {
                    "uri": "turing://strategies",
                    "name": "策略模板",
                    "description": "Turing 的任务策略模板（bug_fix / feature / refactor 等）",
                    "mimeType": "application/json",
                },
                {
                    "uri": "turing://evolution",
                    "name": "进化日志",
                    "description": "Turing 的反思记录和进化数据",
                    "mimeType": "application/json",
                },
                {
                    "uri": "turing://gap_analysis",
                    "name": "能力差距分析",
                    "description": "与顶尖 AI 编程工具的差距分析报告",
                    "mimeType": "application/json",
                },
            ],
        }

    def _handle_resources_read(self, params: dict) -> dict:
        """处理 resources/read"""
        import os
        uri = params.get("uri", "")
        data_dir = os.environ.get("TURING_DATA_DIR", "turing_data")

        resource_map = {
            "turing://strategies": f"{data_dir}/persistent_memory/strategies",
            "turing://evolution": f"{data_dir}/evolution/reflections.json",
            "turing://gap_analysis": f"{data_dir}/evolution/gap_analysis.json",
        }
        path = resource_map.get(uri)
        if not path:
            return {"contents": [{"uri": uri, "text": f"未知资源: {uri}", "mimeType": "text/plain"}]}

        try:
            if os.path.isdir(path):
                # 目录：列出所有文件内容
                result_parts = []
                for fname in sorted(os.listdir(path)):
                    fpath = os.path.join(path, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "r", encoding="utf-8") as f:
                            result_parts.append(f"--- {fname} ---\n{f.read()}")
                text = "\n\n".join(result_parts) if result_parts else "(empty)"
            else:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            return {"contents": [{"uri": uri, "text": text, "mimeType": "application/json"}]}
        except FileNotFoundError:
            return {"contents": [{"uri": uri, "text": f"文件不存在: {path}", "mimeType": "text/plain"}]}

    def _handle_ping(self, params: dict) -> dict:
        """处理 ping"""
        return {}

    def _send_result(self, req_id: Any, result: dict) -> None:
        """发送 JSON-RPC 成功响应"""
        msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
        self._write(msg)

    def _send_error(self, req_id: Any, code: int, message: str) -> None:
        """发送 JSON-RPC 错误响应"""
        msg = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        self._write(msg)

    def _write(self, msg: dict) -> None:
        """写入 stdout（JSON + 换行）"""
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()


def main():
    """MCP 服务端入口"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [MCP-Server] %(message)s",
        stream=sys.stderr,  # 日志输出到 stderr，stdout 留给 JSON-RPC
    )
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
