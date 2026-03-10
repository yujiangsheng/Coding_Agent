"""命令执行工具

提供 run_command 工具，在子进程中执行 Shell 命令并返回输出。

安全约束：
- 执行前经过 ``_check_command_security()`` 检查命令黑名单
- 输出超过 50K 字符时自动截断，防止占满上下文窗口
- 支持自定义超时（默认 30s）
"""

from __future__ import annotations

import subprocess

from turing.tools.registry import tool


def _check_command_security(command: str) -> str | None:
    """检查命令安全性，返回错误信息或 None"""
    from turing.config import Config
    cfg = Config.load()
    blocked = cfg.get("security.blocked_commands", [])
    for pattern in blocked:
        if pattern in command:
            return f"安全限制：禁止执行包含 '{pattern}' 的命令"
    return None


@tool(
    name="run_command",
    description="在终端执行 shell 命令并返回输出。有安全限制，禁止执行破坏性命令。支持自定义超时和工作目录。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "timeout": {
                "type": "integer",
                "description": "超时秒数，默认 30，最大 300",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（可选，默认使用 workspace_root）",
            },
        },
        "required": ["command"],
    },
)
def run_command(command: str, timeout: int = 30, cwd: str = None) -> dict:
    err = _check_command_security(command)
    if err:
        return {"error": err}

    timeout = min(max(timeout, 5), 300)  # 限制 5-300s

    from turing.config import Config
    cfg = Config.load()
    workspace = cwd or cfg.get("security.workspace_root", None) or None

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
        )

        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr

        if len(output) > 50000:
            output = output[:25000] + "\n...(输出截断)...\n" + output[-25000:]

        return {
            "exit_code": result.returncode,
            "output": output.strip(),
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"命令超时（>{timeout}s）: {command[:100]}"}
    except Exception as ex:
        return {"error": f"执行命令失败: {ex}"}
