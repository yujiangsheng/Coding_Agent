"""安全防护系统（v3.0 — P0 安全增强）

提供三大安全能力（对标 Claude Code 的权限系统 + Devin 的沙箱隔离）：

1. **危险操作确认** — 删除文件/git push/系统命令等需二次确认
2. **沙箱执行环境** — 可选 Docker 容器隔离执行
3. **操作审计日志** — 记录所有副作用操作

权限等级::

    ALLOW      — 始终允许（只读操作）
    CONFIRM    — 需用户确认后执行
    DENY       — 始终拒绝

沙箱模式::

    host       — 直接在宿主机执行（默认，向后兼容）
    docker     — 在 Docker 容器中执行命令
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class Permission(Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass
class AuditEntry:
    """审计日志条目"""
    timestamp: float
    tool: str
    args: dict
    permission: str
    approved: bool
    user_response: str = ""


class SafetyGuard:
    """安全防护系统

    - 分析工具调用的风险等级
    - 对危险操作请求用户确认
    - 记录审计日志
    """

    # 危险命令模式（正则）
    DANGEROUS_COMMAND_PATTERNS = [
        r"\brm\s+(-[rRf]+\s+|.*--recursive)",  # rm -rf / rm -r
        r"\bgit\s+push\b.*--force",              # git push --force
        r"\bgit\s+reset\s+--hard\b",             # git reset --hard
        r"\bsudo\b",                              # sudo
        r"\bchmod\s+777\b",                       # chmod 777
        r"\bcurl\b.*\|\s*bash",                   # curl | bash
        r"\bwget\b.*\|\s*bash",                   # wget | bash
        r"\bdocker\s+rm\b",                       # docker rm
        r"\bkill\s+-9\b",                         # kill -9
        r"\bnpm\s+publish\b",                     # npm publish
        r"\bpip\s+install\b.*--break-system",     # pip --break-system
    ]

    # 需要确认的工具+条件映射
    CONFIRM_RULES: list[dict] = [
        # 文件删除
        {"tool": "delete_file", "condition": "always",
         "message": "即将删除文件/目录: {path}"},
        # 批量编辑
        {"tool": "batch_edit", "condition": lambda args: not args.get("dry_run", True),
         "message": "即将执行批量编辑（非 dry_run 模式）"},
        # git push
        {"tool": "run_command", "condition": lambda args: "git push" in args.get("command", ""),
         "message": "即将执行 git push: {command}"},
        # git reset --hard
        {"tool": "run_command",
         "condition": lambda args: "git reset --hard" in args.get("command", ""),
         "message": "即将执行 git reset --hard（不可逆）: {command}"},
        # 匹配危险命令模式
        {"tool": "run_command", "condition": "_check_dangerous_command",
         "message": "检测到潜在危险命令: {command}"},
    ]

    def __init__(self, mode: str = "interactive", auto_approve: bool = False):
        """
        Args:
            mode: 'interactive' (默认，CLI 交互确认) 或 'api' (通过回调确认)
            auto_approve: 是否自动批准所有操作（仅用于测试）
        """
        self._mode = mode
        self._auto_approve = auto_approve
        self._audit_log: list[AuditEntry] = []
        self._confirm_callback: Callable | None = None
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_COMMAND_PATTERNS
        ]
        # 项目级规则（通过 load_project_rules 加载）
        self._project_allow: set[str] = set()
        self._project_deny: set[str] = set()
        self._project_blocked_paths: set[str] = set()
        # 秘密检测模式（v3.2）
        self._secret_patterns = [
            re.compile(p, re.IGNORECASE) for p in [
                r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}",
                r"(?:secret|token|password|passwd|pwd)\s*[:=]\s*['\"][^\s'\"]{8,}",
                r"(?:aws_access_key_id|aws_secret_access_key)\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{20,}",
                r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID
                r"sk-[a-zA-Z0-9]{32,}",  # OpenAI API key
                r"ghp_[a-zA-Z0-9]{36}",  # GitHub PAT
                r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
            ]
        ]

    def set_confirm_callback(self, callback: Callable[[str], bool]):
        """设置外部确认回调（用于 Web UI / API 模式）"""
        self._confirm_callback = callback

    def load_project_rules(self, rules: dict):
        """加载项目级安全规则（v3.2 — 对标 Claude Code .claude/settings.json）

        支持的规则键:
        - allow_tools: list[str] — 始终允许（跳过确认）的工具
        - deny_tools: list[str] — 始终拒绝的工具
        - confirm_patterns: list[str] — 额外需要确认的命令正则
        - blocked_paths: list[str] — 禁止访问的路径
        """
        self._project_allow = set(rules.get("allow_tools", []))
        self._project_deny = set(rules.get("deny_tools", []))
        self._project_blocked_paths = set(rules.get("blocked_paths", []))

        # 追加自定义确认模式
        for pattern in rules.get("confirm_patterns", []):
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
                self._compiled_patterns.append(compiled)
            except re.error:
                pass

    def check_permission(self, tool_name: str, tool_args: dict) -> tuple[Permission, str]:
        """检查工具调用的权限等级

        Returns:
            (Permission, message) — 权限等级和说明消息
        """
        # P1: 项目级拒绝列表优先
        if tool_name in self._project_deny:
            return Permission.DENY, f"项目规则禁止使用工具: {tool_name}"

        # P1: 项目级允许列表（跳过确认）
        if tool_name in self._project_allow:
            return Permission.ALLOW, ""

        # P2: 秘密检测 — 检查工具参数中是否包含敏感信息
        secret_warning = self._check_secrets(tool_args)
        if secret_warning:
            return Permission.CONFIRM, f"检测到可能的敏感信息: {secret_warning}"

        # P1: 项目级路径黑名单
        for key in ("path", "file_path", "command"):
            val = tool_args.get(key, "")
            for blocked in self._project_blocked_paths:
                if blocked and blocked in val:
                    return Permission.DENY, f"路径被项目规则禁止: {blocked}"

        for rule in self.CONFIRM_RULES:
            if rule["tool"] != tool_name:
                continue

            condition = rule["condition"]
            matched = False

            if condition == "always":
                matched = True
            elif condition == "_check_dangerous_command":
                matched = self._is_dangerous_command(tool_args.get("command", ""))
            elif callable(condition):
                try:
                    matched = condition(tool_args)
                except Exception:
                    pass

            if matched:
                msg = rule["message"].format(**tool_args)
                return Permission.CONFIRM, msg

        return Permission.ALLOW, ""

    def _check_secrets(self, args: dict) -> str | None:
        """检测工具参数中是否包含 API 密钥、密码等敏感信息（v3.2）"""
        for key, val in args.items():
            if not isinstance(val, str):
                continue
            for pattern in self._secret_patterns:
                match = pattern.search(val)
                if match:
                    # 返回脱敏后的提示
                    matched_text = match.group()
                    masked = matched_text[:8] + "***" + matched_text[-4:]
                    return f"参数 '{key}' 中包含疑似密钥: {masked}"
        return None

    def request_confirmation(self, tool_name: str, tool_args: dict,
                             message: str) -> bool:
        """请求用户确认危险操作

        Returns:
            True = 用户批准, False = 用户拒绝
        """
        if self._auto_approve:
            self._log_audit(tool_name, tool_args, "confirm", True, "auto_approve")
            return True

        if self._confirm_callback:
            approved = self._confirm_callback(message)
            self._log_audit(tool_name, tool_args, "confirm", approved, "callback")
            return approved

        # CLI 交互模式
        try:
            print(f"\n⚠️  安全确认: {message}")
            print(f"   工具: {tool_name}")
            response = input("   是否继续? [y/N]: ").strip().lower()
            approved = response in ("y", "yes")
            self._log_audit(tool_name, tool_args, "confirm", approved, response)
            return approved
        except (EOFError, KeyboardInterrupt):
            self._log_audit(tool_name, tool_args, "confirm", False, "interrupted")
            return False

    def _is_dangerous_command(self, command: str) -> bool:
        """检测命令是否匹配危险模式"""
        return any(p.search(command) for p in self._compiled_patterns)

    def _log_audit(self, tool: str, args: dict, permission: str,
                   approved: bool, user_response: str = ""):
        """记录审计日志（内存 + 磁盘持久化）"""
        entry = AuditEntry(
            timestamp=time.time(),
            tool=tool,
            args={k: str(v)[:200] for k, v in args.items()},
            permission=permission,
            approved=approved,
            user_response=user_response,
        )
        self._audit_log.append(entry)
        # 只保留最近 500 条
        if len(self._audit_log) > 500:
            self._audit_log = self._audit_log[-500:]

        # v3.2: 持久化到 JSONL 文件
        self._persist_audit_entry(entry)

    def _persist_audit_entry(self, entry: AuditEntry):
        """将审计条目追加写入磁盘（JSONL 格式）"""
        try:
            audit_dir = Path("turing_data")
            audit_dir.mkdir(parents=True, exist_ok=True)
            audit_file = audit_dir / "audit_log.jsonl"
            import json as _json
            record = {
                "timestamp": entry.timestamp,
                "tool": entry.tool,
                "args": entry.args,
                "permission": entry.permission,
                "approved": entry.approved,
                "user_response": entry.user_response,
            }
            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(_json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # 持久化失败不影响主流程

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """获取最近的审计日志"""
        entries = self._audit_log[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "tool": e.tool,
                "args": e.args,
                "permission": e.permission,
                "approved": e.approved,
            }
            for e in entries
        ]


class SandboxExecutor:
    """沙箱执行环境（对标 Devin 的 Docker 隔离执行）

    支持在 Docker 容器中执行命令，隔离文件系统和网络。
    当 Docker 不可用时优雅降级到宿主机执行。
    """

    def __init__(self, mode: str = "host", image: str = "python:3.11-slim",
                 workspace_mount: str = None):
        """
        Args:
            mode: 'host' (宿主机) 或 'docker' (容器隔离)
            image: Docker 镜像名
            workspace_mount: 挂载到容器的工作目录
        """
        self._mode = mode
        self._image = image
        self._workspace = workspace_mount
        self._container_id: str | None = None
        self._docker_available: bool | None = None

        # v8.0: 注册退出清理钩子，防止 Docker 容器泄漏
        import atexit
        atexit.register(self.cleanup)

    @property
    def mode(self) -> str:
        return self._mode

    def is_docker_available(self) -> bool:
        """检测 Docker 是否可用"""
        if self._docker_available is not None:
            return self._docker_available
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5,
            )
            self._docker_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._docker_available = False
        return self._docker_available

    def execute(self, command: str, timeout: int = 30, cwd: str = None) -> dict:
        """在沙箱环境中执行命令"""
        if self._mode == "docker" and self.is_docker_available():
            return self._docker_execute(command, timeout, cwd)
        return self._host_execute(command, timeout, cwd)

    def _host_execute(self, command: str, timeout: int, cwd: str = None) -> dict:
        """在宿主机执行（原始行为）"""
        import subprocess
        try:
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )
            output = result.stdout
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr
            return {
                "exit_code": result.returncode,
                "output": output.strip(),
                "success": result.returncode == 0,
                "sandbox": "host",
            }
        except subprocess.TimeoutExpired:
            return {"error": f"命令超时（>{timeout}s）"}
        except Exception as e:
            return {"error": f"执行失败: {e}"}

    def _docker_execute(self, command: str, timeout: int, cwd: str = None) -> dict:
        """在 Docker 容器中执行"""
        import subprocess

        # 确保容器运行
        if not self._container_id:
            self._start_container()

        if not self._container_id:
            # Docker 启动失败，降级到宿主机
            logger.warning("Docker 容器启动失败，降级到宿主机执行")
            return self._host_execute(command, timeout, cwd)

        docker_cmd = ["docker", "exec"]
        if cwd:
            docker_cmd.extend(["-w", cwd])
        docker_cmd.extend([self._container_id, "bash", "-c", command])

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True, text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr
            return {
                "exit_code": result.returncode,
                "output": output.strip(),
                "success": result.returncode == 0,
                "sandbox": "docker",
                "container": self._container_id,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"命令超时（>{timeout}s）", "sandbox": "docker"}
        except Exception as e:
            return {"error": f"Docker 执行失败: {e}"}

    def _validate_mount_path(self, path: str) -> bool:
        """验证挂载路径安全性，防止目录逃逸"""
        from pathlib import Path as _Path
        resolved = _Path(path).resolve()
        # 禁止挂载系统关键目录
        forbidden = {"/", "/etc", "/usr", "/bin", "/sbin", "/boot",
                     "/dev", "/proc", "/sys", "/var", "/root"}
        if str(resolved) in forbidden:
            logger.error("拒绝挂载系统关键目录: %s", path)
            return False
        # 禁止包含 .. 的路径
        if ".." in str(path):
            logger.error("拒绝包含 '..' 的挂载路径: %s", path)
            return False
        return True

    def _start_container(self):
        """启动 Docker 容器（v3.1 — 增强安全隔离）"""
        import subprocess

        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", f"turing-sandbox-{int(time.time())}",
            "--network", "none",       # 网络隔离
            "--memory", "512m",        # 内存限制
            "--cpus", "1",             # CPU 限制
            "--pids-limit", "256",     # 进程数限制（防 fork 炸弹）
            "--user", "nobody",        # 非 root 用户执行
            "--cap-drop=ALL",          # 丢弃所有 Linux capabilities
            "--security-opt", "no-new-privileges",  # 禁止提权
            "--ipc", "private",        # IPC 隔离
        ]

        if self._workspace:
            if not self._validate_mount_path(self._workspace):
                logger.error("挂载路径验证失败，拒绝启动容器")
                return
            cmd.extend(["-v", f"{self._workspace}:/workspace:rw", "-w", "/workspace"])
        cmd.extend([self._image, "sleep", "3600"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                self._container_id = result.stdout.strip()[:12]
                logger.info(f"Docker 沙箱启动: {self._container_id}")
            else:
                logger.warning(f"Docker 启动失败: {result.stderr}")
        except Exception as e:
            logger.warning(f"Docker 启动异常: {e}")

    def container_stats(self) -> dict | None:
        """获取容器资源使用统计"""
        if not self._container_id:
            return None
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format",
                 '{"cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","pids":"{{.PIDs}}"}',
                 self._container_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout.strip())
        except Exception:
            pass
        return None

    def cleanup(self):
        """清理容器"""
        if self._container_id:
            import subprocess
            try:
                subprocess.run(
                    ["docker", "stop", self._container_id],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
            self._container_id = None
