"""命令执行工具（v2.0 — 持久化 Shell 会话）

提供两种命令执行模式（对标 Claude Code / Devin 的持久终端）：
- run_command    — 在持久 Shell 会话中执行命令，环境变量和 cwd 跨调用保持
- run_background — 在后台启动长期运行的进程（如 dev server），返回进程 ID

安全约束：
- 执行前经过 ``_check_command_security()`` 检查命令黑名单
- 输出超过 50K 字符时自动截断，防止占满上下文窗口
- 支持自定义超时（默认 30s）

持久化 Shell 特性（v2.0 新增）：
- 环境变量在命令之间持久化（如 export FOO=bar 后续命令可用）
- 工作目录跨调用保持（cd 到新目录后续命令自动继承）
- 后台进程管理（启动 dev server 等长时间进程）
"""

from __future__ import annotations

import os
import subprocess
import threading

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


def _truncate_output(output: str, limit: int = 50000) -> str:
    """截断过长输出，保留首尾"""
    if len(output) > limit:
        half = limit // 2
        return output[:half] + "\n...(输出截断)...\n" + output[-half:]
    return output


# ── 持久化 Shell 会话管理 ──────────────────────────
class _ShellSession:
    """持久化 Shell 会话，环境变量和工作目录在命令之间保持"""

    def __init__(self, cwd: str | None = None):
        """初始化 Shell 会话，从 config 或 os.getcwd() 设置工作目录。"""
        from turing.config import Config
        cfg = Config.load()
        self._cwd = cwd or cfg.get("security.workspace_root", None) or os.getcwd()
        self._env = os.environ.copy()

    @property
    def cwd(self) -> str:
        return self._cwd

    def run(self, command: str, timeout: int = 30) -> dict:
        """在持久化环境中执行命令，捕获 cwd 和 env 变化"""
        # 包装命令：执行后输出当前 cwd 和 env（用分隔符隔开）
        separator = "__TURING_SESSION_SEP__"
        wrapped = (
            f"{{ {command} ; }} 2>&1\n"
            f"__exit_code__=$?\n"
            f"echo '{separator}'\n"
            f"pwd\n"
            f"echo '{separator}'\n"
            f"env\n"
            f"exit $__exit_code__\n"
        )

        try:
            result = subprocess.run(
                ["bash", "-c", wrapped],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
                env=self._env,
            )

            parts = result.stdout.split(separator)
            user_output = parts[0].rstrip("\n") if parts else result.stdout

            # 更新 cwd
            if len(parts) > 1:
                new_cwd = parts[1].strip()
                if new_cwd and os.path.isdir(new_cwd):
                    self._cwd = new_cwd

            # 更新 env（解析 key=value）
            if len(parts) > 2:
                env_text = parts[2].strip()
                new_env = {}
                for line in env_text.split("\n"):
                    eq = line.find("=")
                    if eq > 0:
                        new_env[line[:eq]] = line[eq + 1:]
                if new_env:
                    self._env = new_env

            if result.stderr:
                user_output += "\n[stderr]\n" + result.stderr

            return {
                "exit_code": result.returncode,
                "output": _truncate_output(user_output).strip(),
                "success": result.returncode == 0,
                "cwd": self._cwd,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"命令超时（>{timeout}s）: {command[:100]}"}
        except Exception as ex:
            return {"error": f"执行命令失败: {ex}"}


# 全局持久会话（单例）
_session: _ShellSession | None = None


def _get_session(cwd: str | None = None) -> _ShellSession:
    """获取全局 Shell 会话单例。"""
    global _session
    if _session is None:
        _session = _ShellSession(cwd)
    return _session


# ── 后台进程管理 ──────────────────────────────────
_bg_processes: dict[int, dict] = {}  # pid → {"process", "command", "output_lines"}
_bg_lock = threading.Lock()


def _collect_bg_output(pid: int, proc: subprocess.Popen):
    """后台线程：收集后台进程输出（最多保留最近 200 行）"""
    max_lines = 200
    try:
        for line in proc.stdout:
            with _bg_lock:
                if pid in _bg_processes:
                    buf = _bg_processes[pid]["output_lines"]
                    buf.append(line)
                    if len(buf) > max_lines:
                        _bg_processes[pid]["output_lines"] = buf[-max_lines:]
    except Exception:
        pass


@tool(
    name="run_command",
    description="在持久化 Shell 会话中执行命令。环境变量和工作目录在命令之间保持（如 export / cd）。支持自定义超时和工作目录。",
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
                "description": "工作目录（可选，默认继承上次 cwd 或 workspace_root）",
            },
        },
        "required": ["command"],
    },
)
def run_command(command: str, timeout: int = 30, cwd: str = None) -> dict:
    """在持久化 Shell 中执行命令，env/cwd 跨调用保持。"""
    err = _check_command_security(command)
    if err:
        return {"error": err}

    timeout = min(max(timeout, 5), 300)
    session = _get_session(cwd)

    # 如果显式指定 cwd，临时切换
    if cwd and os.path.isdir(cwd):
        session._cwd = cwd

    return session.run(command, timeout=timeout)


@tool(
    name="run_background",
    description="在后台启动长期运行的进程（如 dev server、watcher）。返回进程 PID，可用 check_background 查看输出或 stop_background 终止。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的后台命令"},
            "cwd": {
                "type": "string",
                "description": "工作目录（可选）",
            },
        },
        "required": ["command"],
    },
)
def run_background(command: str, cwd: str = None) -> dict:
    """启动后台进程（服务器、watch 等），返回 PID。"""
    err = _check_command_security(command)
    if err:
        return {"error": err}

    from turing.config import Config
    cfg = Config.load()
    workspace = cwd or cfg.get("security.workspace_root", None) or os.getcwd()

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=workspace,
        )
        pid = proc.pid

        with _bg_lock:
            _bg_processes[pid] = {
                "process": proc,
                "command": command,
                "output_lines": [],
            }

        # 启动输出收集线程
        t = threading.Thread(target=_collect_bg_output, args=(pid, proc), daemon=True)
        t.start()

        return {
            "status": "ok",
            "pid": pid,
            "command": command,
            "message": f"后台进程已启动 (PID: {pid})，使用 check_background 查看输出",
        }
    except Exception as ex:
        return {"error": f"启动后台进程失败: {ex}"}


@tool(
    name="check_background",
    description="检查后台进程的状态和最近输出。不指定 PID 则列出所有后台进程。",
    parameters={
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "进程 PID（可选，不指定则列出所有后台进程）",
            },
        },
        "required": [],
    },
)
def check_background(pid: int = None) -> dict:
    """查看后台进程状态和最新输出。"""
    with _bg_lock:
        if pid is not None:
            info = _bg_processes.get(pid)
            if not info:
                return {"error": f"未找到 PID={pid} 的后台进程"}
            proc = info["process"]
            alive = proc.poll() is None
            return {
                "pid": pid,
                "command": info["command"],
                "running": alive,
                "exit_code": proc.returncode if not alive else None,
                "recent_output": "".join(info["output_lines"][-50:]),
            }
        else:
            # 列出所有
            result = []
            for p, info in _bg_processes.items():
                proc = info["process"]
                alive = proc.poll() is None
                result.append({
                    "pid": p,
                    "command": info["command"][:80],
                    "running": alive,
                    "exit_code": proc.returncode if not alive else None,
                })
            return {"processes": result, "count": len(result)}


@tool(
    name="stop_background",
    description="终止一个后台进程。",
    parameters={
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "要终止的进程 PID",
            },
        },
        "required": ["pid"],
    },
)
def stop_background(pid: int) -> dict:
    """终止指定后台进程（SIGTERM）。"""
    with _bg_lock:
        info = _bg_processes.get(pid)
        if not info:
            return {"error": f"未找到 PID={pid} 的后台进程"}
        proc = info["process"]
        if proc.poll() is not None:
            return {"status": "already_stopped", "exit_code": proc.returncode}
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        del _bg_processes[pid]
    return {"status": "ok", "pid": pid, "message": "后台进程已终止"}


# ────────────────── 自动修复工具 ──────────────────


@tool(
    name="auto_fix",
    description="自动检测并修复代码文件中的常见问题：运行 lint、收集错误、"
                "然后尝试自动修复（使用 ruff --fix / eslint --fix 等）。"
                "返回修复前后的差异。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要修复的文件或目录路径",
            },
            "dry_run": {
                "type": "boolean",
                "description": "仅检测不修复（默认 false）",
            },
        },
        "required": ["path"],
    },
)
def auto_fix(path: str, dry_run: bool = False) -> dict:
    """自动检测并修复代码问题。"""
    import shutil
    from pathlib import Path

    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    results = {"fixes": [], "errors_before": 0, "errors_after": 0}

    # Python: ruff
    is_python = p.suffix == ".py" or (p.is_dir() and any(p.rglob("*.py")))
    if is_python and shutil.which("ruff"):
        # Step 1: 检测当前问题数
        check_cmd = ["ruff", "check", "--output-format=text", str(p)]
        try:
            before = subprocess.run(
                check_cmd, capture_output=True, text=True, timeout=30
            )
            before_lines = [l for l in before.stdout.strip().split("\n") if l.strip()]
            results["errors_before"] = len(before_lines)
            results["sample_errors"] = before_lines[:10]
        except Exception as e:
            return {"error": f"ruff check 失败: {e}"}

        if dry_run:
            return {
                "status": "dry_run",
                "tool": "ruff",
                "errors_found": results["errors_before"],
                "sample_errors": results.get("sample_errors", []),
            }

        # Step 2: 自动修复
        fix_cmd = ["ruff", "check", "--fix", str(p)]
        try:
            subprocess.run(fix_cmd, capture_output=True, text=True, timeout=30)
        except Exception as e:
            return {"error": f"ruff fix 失败: {e}"}

        # Step 3: format
        if shutil.which("ruff"):
            fmt_cmd = ["ruff", "format", str(p)]
            try:
                subprocess.run(fmt_cmd, capture_output=True, text=True, timeout=30)
            except Exception:
                pass

        # Step 4: 重新检测
        try:
            after = subprocess.run(
                check_cmd, capture_output=True, text=True, timeout=30
            )
            after_lines = [l for l in after.stdout.strip().split("\n") if l.strip()]
            results["errors_after"] = len(after_lines)
        except Exception:
            results["errors_after"] = -1

        fixed_count = max(0, results["errors_before"] - results["errors_after"])
        results["fixes"].append({
            "tool": "ruff",
            "fixed": fixed_count,
            "remaining": results["errors_after"],
        })

        return {
            "status": "ok",
            "tool": "ruff",
            "errors_before": results["errors_before"],
            "errors_after": results["errors_after"],
            "fixed": fixed_count,
            "remaining_errors": after_lines[:10] if results["errors_after"] > 0 else [],
        }

    # JavaScript/TypeScript: eslint
    is_js = p.suffix in (".js", ".ts", ".jsx", ".tsx") or (
        p.is_dir() and ((p / "package.json").exists() or any(p.rglob("*.js")))
    )
    if is_js and shutil.which("npx"):
        action = "--fix" if not dry_run else ""
        cmd = f"npx eslint {action} {path}".strip()
        try:
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=60
            )
            return {
                "status": "ok" if not dry_run else "dry_run",
                "tool": "eslint",
                "output": result.stdout[-2000:],
            }
        except Exception as e:
            return {"error": f"eslint 失败: {e}"}

    return {"error": "未找到可用的自动修复工具（需要 ruff 或 eslint）"}
