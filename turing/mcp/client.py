"""MCP 客户端

连接外部 MCP 服务器（stdio / SSE 传输），发现服务器提供的工具，
并将其包装为 Turing ToolDef 注册到全局工具注册表中。

支持两种传输方式：
- **stdio** — 启动子进程，通过 stdin/stdout 通信（本地 MCP 服务器）
- **sse** — 通过 HTTP Server-Sent Events 通信（远程 MCP 服务器）

MCP 协议实现基于 JSON-RPC 2.0，核心消息：
- initialize — 握手，交换能力声明
- tools/list — 发现服务器提供的工具
- tools/call — 调用指定工具
- notifications/initialized — 初始化完成通知
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import time
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

# JSON-RPC 2.0 消息构建

_request_id_counter = 0
_id_lock = threading.Lock()


def _next_id() -> int:
    global _request_id_counter
    with _id_lock:
        _request_id_counter += 1
        return _request_id_counter


def _jsonrpc_request(method: str, params: dict | None = None, req_id: int | None = None) -> dict:
    """构造 JSON-RPC 2.0 请求"""
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if req_id is not None:
        msg["id"] = req_id
    return msg


def _jsonrpc_notification(method: str, params: dict | None = None) -> dict:
    """构造 JSON-RPC 2.0 通知（无 id）"""
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


class MCPTransport:
    """MCP 传输层抽象基类"""

    def send(self, message: dict) -> None:
        raise NotImplementedError

    def receive(self, timeout: float = 30.0) -> dict | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class StdioTransport(MCPTransport):
    """stdio 传输：通过子进程 stdin/stdout 通信

    每条 JSON-RPC 消息以换行符分隔，无 Content-Length 头。
    """

    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
            text=True,
            bufsize=1,
        )
        self._read_lock = threading.Lock()

    def send(self, message: dict) -> None:
        if self._process.stdin is None:
            raise RuntimeError("MCP 子进程 stdin 不可用")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

    def receive(self, timeout: float = 30.0) -> dict | None:
        import select
        if self._process.stdout is None:
            return None
        with self._read_lock:
            # 使用 select 做非阻塞读取
            ready, _, _ = select.select([self._process.stdout], [], [], timeout)
            if not ready:
                return None
            line = self._process.stdout.readline()
            if not line:
                return None
            try:
                return json.loads(line.strip())
            except json.JSONDecodeError:
                logger.warning("MCP stdio: 无法解析响应: %s", line.strip()[:200])
                return None

    def close(self) -> None:
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.terminate()
            self._process.wait(timeout=5)
        except Exception:
            self._process.kill()

    def __del__(self):
        """v7.0: 安全网 — 防止子进程泄漏"""
        try:
            self.close()
        except Exception:
            pass


class SSETransport(MCPTransport):
    """SSE 传输：通过 HTTP POST 发送请求，通过 SSE 接收响应

    POST 端点：{base_url}/message
    SSE 端点：{base_url}/sse
    """

    def __init__(self, base_url: str, headers: dict[str, str] | None = None):
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._response_queue: queue.Queue = queue.Queue()
        self._sse_thread: threading.Thread | None = None
        self._running = False
        self._start_sse_listener()

    def _start_sse_listener(self) -> None:
        """启动后台线程监听 SSE 事件"""
        self._running = True
        self._sse_thread = threading.Thread(target=self._listen_sse, daemon=True)
        self._sse_thread.start()

    def _listen_sse(self) -> None:
        """后台线程：持续读取 SSE 流（v11.0: 批量读取优化）"""
        url = f"{self._base_url}/sse"
        req = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                buf = bytearray()
                while self._running:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    # 处理完整的 SSE 消息（\n\n 分隔）
                    while b"\n\n" in buf:
                        msg_end = buf.index(b"\n\n") + 2
                        raw = buf[:msg_end].decode("utf-8", errors="replace")
                        buf = buf[msg_end:]
                        for line in raw.strip().split("\n"):
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    self._response_queue.put(json.loads(data_str))
                                except json.JSONDecodeError:
                                    pass
        except Exception as e:
            logger.warning("MCP SSE 连接断开: %s", e)

    def send(self, message: dict) -> None:
        url = f"{self._base_url}/message"
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**self._headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except urllib.error.URLError as e:
            raise ConnectionError(f"MCP SSE POST 失败: {e}") from e

    def receive(self, timeout: float = 30.0) -> dict | None:
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._running = False


class MCPClient:
    """MCP 客户端

    连接单个 MCP 服务器，发现工具并提供调用接口。

    Usage::

        # stdio 模式
        client = MCPClient.from_stdio(["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
        tools = client.list_tools()
        result = client.call_tool("read_file", {"path": "/tmp/hello.txt"})

        # SSE 模式
        client = MCPClient.from_sse("http://localhost:3000")
        tools = client.list_tools()
    """

    def __init__(self, transport: MCPTransport, server_name: str = "unknown"):
        self._transport = transport
        self.server_name = server_name
        self._server_info: dict = {}
        self._tools: list[dict] = []
        self._initialized = False
        self._pending: dict[int, dict | None] = {}

    @classmethod
    def from_stdio(
        cls,
        command: list[str],
        server_name: str | None = None,
        env: dict[str, str] | None = None,
    ) -> "MCPClient":
        """通过 stdio 连接本地 MCP 服务器"""
        name = server_name or command[0].split("/")[-1]
        transport = StdioTransport(command, env=env)
        try:
            client = cls(transport, server_name=name)
            client._handshake()
            return client
        except Exception:
            transport.close()
            raise

    @classmethod
    def from_sse(
        cls,
        base_url: str,
        server_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> "MCPClient":
        """通过 SSE 连接远程 MCP 服务器"""
        name = server_name or base_url.split("//")[-1].split("/")[0]
        transport = SSETransport(base_url, headers=headers)
        client = cls(transport, server_name=name)
        client._handshake()
        return client

    def _handshake(self) -> None:
        """MCP 初始化握手"""
        req_id = _next_id()
        init_msg = _jsonrpc_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": False},
            },
            "clientInfo": {
                "name": "turing-agent",
                "version": "3.5.0",
            },
        }, req_id=req_id)
        self._transport.send(init_msg)
        resp = self._wait_response(req_id, timeout=15.0)
        if resp and "result" in resp:
            self._server_info = resp["result"].get("serverInfo", {})
            logger.info("MCP 握手成功: %s (protocol=%s)",
                        self._server_info.get("name", "unknown"),
                        resp["result"].get("protocolVersion", "?"))
        else:
            logger.warning("MCP 握手响应异常: %s", resp)

        # 发送 initialized 通知
        self._transport.send(_jsonrpc_notification("notifications/initialized"))
        self._initialized = True

    def _wait_response(self, req_id: int, timeout: float = 30.0) -> dict | None:
        """等待指定 id 的响应，跳过通知"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self._transport.receive(timeout=min(1.0, deadline - time.time()))
            if msg is None:
                continue
            # 跳过通知（无 id 的消息）
            if "id" not in msg:
                continue
            if msg.get("id") == req_id:
                return msg
        return None

    def list_tools(self) -> list[dict]:
        """发现服务器提供的工具列表

        Returns:
            [{"name": "...", "description": "...", "inputSchema": {...}}, ...]
        """
        req_id = _next_id()
        self._transport.send(_jsonrpc_request("tools/list", {}, req_id=req_id))
        resp = self._wait_response(req_id)
        if resp and "result" in resp:
            self._tools = resp["result"].get("tools", [])
            return self._tools
        return []

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """调用服务器提供的工具

        Args:
            tool_name: 工具名称
            arguments: 参数字典

        Returns:
            {"content": [...], "isError": bool}
        """
        req_id = _next_id()
        self._transport.send(_jsonrpc_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        }, req_id=req_id))
        resp = self._wait_response(req_id, timeout=60.0)
        if resp is None:
            return {"error": f"MCP 工具调用超时: {tool_name}"}
        if "error" in resp:
            err = resp["error"]
            return {"error": f"MCP 错误 [{err.get('code', '?')}]: {err.get('message', '?')}"}
        result = resp.get("result", {})
        # 将 MCP content 数组转为 Turing 标准 dict
        return _mcp_result_to_dict(result)

    def list_resources(self) -> list[dict]:
        """发现服务器提供的资源列表"""
        req_id = _next_id()
        self._transport.send(_jsonrpc_request("resources/list", {}, req_id=req_id))
        resp = self._wait_response(req_id)
        if resp and "result" in resp:
            return resp["result"].get("resources", [])
        return []

    def read_resource(self, uri: str) -> dict:
        """读取资源"""
        req_id = _next_id()
        self._transport.send(_jsonrpc_request("resources/read", {"uri": uri}, req_id=req_id))
        resp = self._wait_response(req_id, timeout=30.0)
        if resp is None:
            return {"error": f"MCP 资源读取超时: {uri}"}
        if "error" in resp:
            return {"error": resp["error"].get("message", "unknown")}
        result = resp.get("result", {})
        contents = result.get("contents", [])
        if contents:
            return {"content": contents[0].get("text", ""), "uri": uri}
        return {"content": "", "uri": uri}

    def get_server_info(self) -> dict:
        """返回服务器信息"""
        return {
            "name": self.server_name,
            "server_info": self._server_info,
            "initialized": self._initialized,
            "tool_count": len(self._tools),
        }

    def ping(self, timeout: float = 5.0) -> bool:
        """检测 MCP 服务器连接是否存活（v3.1）"""
        if not self._initialized:
            return False
        try:
            req_id = _next_id()
            self._transport.send(_jsonrpc_request("ping", {}, req_id=req_id))
            resp = self._wait_response(req_id, timeout=timeout)
            return resp is not None
        except Exception:
            return False

    def reconnect(self) -> bool:
        """尝试重新连接 MCP 服务器（v3.1）

        仅支持 SSE 传输（无状态可重连）。stdio 需要重建。
        返回 True 表示重连成功。
        """
        try:
            self._initialized = False
            # SSE 传输可直接重新握手
            if isinstance(self._transport, SSETransport):
                self._handshake()
                return self._initialized
            # stdio 传输：检查进程是否存活
            if isinstance(self._transport, StdioTransport):
                proc = self._transport._process
                if proc.poll() is not None:
                    # 进程已退出，无法重连
                    return False
                # 进程存活，尝试重新握手
                self._handshake()
                return self._initialized
            return False
        except Exception as e:
            logger.warning("MCP 重连失败 (%s): %s", self.server_name, e)
            return False

    def close(self) -> None:
        """关闭连接"""
        self._transport.close()
        self._initialized = False


def _mcp_result_to_dict(result: dict) -> dict:
    """将 MCP 工具调用结果转为 Turing 标准格式

    MCP 结果格式: {"content": [{"type": "text", "text": "..."}, ...], "isError": false}
    Turing 格式: {"result": "...", "type": "text"} 或 {"error": "..."}
    """
    is_error = result.get("isError", False)
    content_list = result.get("content", [])
    if not content_list:
        return {"error": "MCP 返回空结果"} if is_error else {"result": ""}

    # 合并所有 text content
    texts = []
    for item in content_list:
        if isinstance(item, dict):
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif item.get("type") == "image":
                texts.append(f"[图片: {item.get('mimeType', 'image/*')}]")
            elif item.get("type") == "resource":
                res = item.get("resource", {})
                texts.append(f"[资源: {res.get('uri', '?')}]\n{res.get('text', '')}")

    combined = "\n".join(texts)
    if is_error:
        return {"error": combined}

    # 尝试解析 JSON 结果
    try:
        parsed = json.loads(combined)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except (json.JSONDecodeError, ValueError):
        return {"result": combined}


def mcp_tool_to_turing_schema(mcp_tool: dict) -> dict:
    """将 MCP 工具定义转为 Turing 工具参数 Schema

    MCP 格式: {"name": "...", "description": "...", "inputSchema": {"type": "object", ...}}
    Turing 格式: {"type": "object", "properties": {...}, "required": [...]}
    """
    schema = mcp_tool.get("inputSchema", {})
    if not schema:
        schema = {"type": "object", "properties": {}, "required": []}
    return schema
