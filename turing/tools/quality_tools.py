"""代码质量工具

为 Turing 补齐代码质量检查能力（对标 Claude Opus 的安全编码和代码检查）：
- lint_code     — 运行 linter（Ruff/flake8/ESLint 等）
- format_code   — 运行代码格式化（black/prettier 等）
- type_check    — 运行类型检查（mypy/pyright/tsc 等）

Claude Opus 的核心优势之一是主动检查代码质量和安全性。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from turing.tools.registry import tool


def _run_quality_cmd(cmd: list[str], cwd: str = ".", timeout: int = 60) -> dict:
    """执行代码质量工具命令（v6.0: shell=False 防注入）"""
    from turing.config import Config
    cfg = Config.load()
    workspace = cfg.get("security.workspace_root", None) or cwd

    try:
        result = subprocess.run(
            cmd, shell=False, capture_output=True, text=True,
            timeout=timeout, cwd=workspace,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if len(output) > 30000:
            output = output[:15000] + "\n...(截断)...\n" + output[-15000:]
        return {
            "exit_code": result.returncode,
            "output": output.strip(),
            "has_issues": result.returncode != 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"命令超时（>{timeout}s）"}
    except Exception as e:
        return {"error": f"执行失败: {e}"}


def _detect_linter(path: str = ".") -> tuple[str, str]:
    """检测可用的 linter"""
    import shutil
    p = Path(path).resolve()

    # Python linters
    if any((p / f).exists() for f in ["pyproject.toml", "requirements.txt", "setup.py", "*.py"]):
        if shutil.which("ruff"):
            return "ruff", "ruff check"
        if shutil.which("flake8"):
            return "flake8", "flake8"
        if shutil.which("pylint"):
            return "pylint", "pylint"
        return "ruff", "python3 -m ruff check"

    # JS/TS linters
    if (p / "package.json").exists():
        if (p / ".eslintrc.js").exists() or (p / ".eslintrc.json").exists() or (p / "eslint.config.js").exists():
            return "eslint", "npx eslint"
        return "eslint", "npx eslint"

    # Go
    if (p / "go.mod").exists():
        return "golangci-lint", "golangci-lint run"

    return "unknown", ""


@tool(
    name="lint_code",
    description="运行代码 linter 检查代码风格和潜在问题。自动检测 Ruff/flake8/ESLint/golangci-lint。可指定文件或目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要检查的文件或目录（默认当前目录）",
            },
            "fix": {
                "type": "boolean",
                "description": "是否自动修复可修复的问题（默认 false）",
            },
        },
        "required": [],
    },
)
def lint_code(path: str = ".", fix: bool = False) -> dict:
    """运行 Linter（自动检测 Ruff/flake8/ESLint 等）。"""
    linter_name, base_cmd = _detect_linter(path)
    if not base_cmd:
        return {"error": "未检测到可用的 linter 工具。请安装 ruff、flake8 或 eslint。"}

    cmd = base_cmd.split()
    if fix and linter_name in ("ruff", "eslint"):
        cmd.append("--fix")

    target = path if path != "." else "."
    cmd.append(target)

    result = _run_quality_cmd(cmd)
    result["linter"] = linter_name
    result["auto_fixed"] = fix and result.get("exit_code", 1) == 0

    # 统计问题数
    output = result.get("output", "")
    issue_count = 0
    for line in output.split("\n"):
        if line.strip() and (":" in line) and not line.startswith(("[", "=", "-", " ")):
            issue_count += 1
    result["issue_count"] = issue_count

    return result


@tool(
    name="format_code",
    description="运行代码格式化工具。自动检测 Black/Ruff format/Prettier 等。可指定文件或目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要格式化的文件或目录（默认当前目录）",
            },
            "check_only": {
                "type": "boolean",
                "description": "仅检查不修改（默认 false，直接格式化）",
            },
        },
        "required": [],
    },
)
def format_code(path: str = ".", check_only: bool = False) -> dict:
    """运行代码格式化（自动检测 Black/Prettier 等）。"""
    import shutil
    p = Path(path).resolve()

    # 检测格式化工具
    formatter = None
    cmd = None

    # Python
    if shutil.which("ruff") and (p.suffix == ".py" or p.is_dir()):
        formatter = "ruff-format"
        cmd = ["ruff", "format"]
        if check_only:
            cmd.append("--check")
        cmd.append(path)
    elif shutil.which("black") and (p.suffix == ".py" or p.is_dir()):
        formatter = "black"
        cmd = ["black"]
        if check_only:
            cmd.append("--check")
        cmd.append(path)

    # JS/TS
    elif shutil.which("npx") and p.suffix in (".js", ".ts", ".jsx", ".tsx", ".json", ".css"):
        formatter = "prettier"
        cmd = ["npx", "prettier", "--check" if check_only else "--write", path]

    # Go
    elif shutil.which("gofmt") and p.suffix == ".go":
        formatter = "gofmt"
        cmd = ["gofmt", "-d" if check_only else "-w", path]

    if not cmd:
        return {
            "error": "未检测到可用的格式化工具。请安装 ruff/black（Python）或 prettier（JS/TS）。",
        }

    result = _run_quality_cmd(cmd)
    result["formatter"] = formatter
    result["check_only"] = check_only
    return result


@tool(
    name="type_check",
    description="运行类型检查器。自动检测 mypy/pyright/tsc 等。可指定文件或目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要检查的文件或目录（默认当前目录）",
            },
            "strict": {
                "type": "boolean",
                "description": "是否使用严格模式（默认 false）",
            },
        },
        "required": [],
    },
)
def type_check(path: str = ".", strict: bool = False) -> dict:
    """运行类型检查（自动检测 mypy/pyright/tsc）。"""
    import shutil
    p = Path(path).resolve()

    checker = None
    cmd = None

    # Python type checkers
    if p.suffix == ".py" or (p.is_dir() and any(p.glob("**/*.py"))):
        if shutil.which("mypy"):
            checker = "mypy"
            cmd = ["mypy"]
            if strict:
                cmd.append("--strict")
            cmd.append(path)
        elif shutil.which("pyright"):
            checker = "pyright"
            cmd = ["pyright", path]
        else:
            checker = "mypy"
            cmd = ["python3", "-m", "mypy"]
            if strict:
                cmd.append("--strict")
            cmd.append(path)

    # TypeScript
    elif p.suffix in (".ts", ".tsx") or (p.is_dir() and (p / "tsconfig.json").exists()):
        checker = "tsc"
        cmd = ["npx", "tsc", "--noEmit"]
        if strict:
            cmd.append("--strict")

    if not cmd:
        return {
            "error": "未检测到可用的类型检查器。请安装 mypy（Python）或确保 TypeScript 环境可用。",
        }

    result = _run_quality_cmd(cmd)
    result["checker"] = checker

    # 统计类型错误数
    output = result.get("output", "")
    error_count = 0
    for line in output.split("\n"):
        if "error:" in line.lower() or "Error:" in line:
            error_count += 1
    result["error_count"] = error_count

    return result


# ────────────────── 安全扫描工具 ──────────────────


@tool(
    name="security_scan",
    description="静态安全扫描：检查代码中的常见安全问题（SQL 注入、XSS、"
                "硬编码密钥、不安全的 eval/exec、路径遍历等）。"
                "优先使用 bandit（Python）或 semgrep，回退到内置正则扫描。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要扫描的文件或目录路径",
            },
            "severity": {
                "type": "string",
                "description": "最低报告级别: low / medium / high（默认 medium）",
                "enum": ["low", "medium", "high"],
            },
        },
        "required": ["path"],
    },
)
def security_scan(path: str, severity: str = "medium") -> dict:
    """静态安全扫描。"""
    import shutil
    import re as _re

    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    # 优先使用 bandit（Python 安全扫描）
    if shutil.which("bandit"):
        sev_map = {"low": "l", "medium": "m", "high": "h"}
        sev_flag = sev_map.get(severity, "m")
        # v10.0: 修正为 list 格式，匹配 _run_quality_cmd 的 shell=False
        cmd = ["bandit", "-r", "-ll", f"-{sev_flag}", "-f", "json", str(p)]
        result = _run_quality_cmd(cmd, timeout=60)
        if result.get("exit_code", 1) in (0, 1):
            try:
                import json as _json
                data = _json.loads(result.get("output", "{}"))
                issues = data.get("results", [])
                return {
                    "status": "ok",
                    "scanner": "bandit",
                    "issues_count": len(issues),
                    "issues": [
                        {
                            "file": i.get("filename", ""),
                            "line": i.get("line_number", 0),
                            "severity": i.get("issue_severity", ""),
                            "confidence": i.get("issue_confidence", ""),
                            "issue": i.get("issue_text", ""),
                            "cwe": i.get("issue_cwe", {}).get("id", ""),
                        }
                        for i in issues[:50]
                    ],
                }
            except Exception:
                pass

    # 回退：内置正则安全检查
    patterns = [
        {"name": "hardcoded_secret", "severity": "high",
         "pattern": r'''(?:password|secret|api_key|token)\s*=\s*['\"][^'"]{8,}['\"]''',
         "description": "疑似硬编码密钥或密码"},
        {"name": "eval_exec", "severity": "high",
         "pattern": r'\b(?:eval|exec)\s*\(',
         "description": "使用 eval/exec，可能导致代码注入"},
        {"name": "sql_injection", "severity": "high",
         "pattern": r'''(?:execute|cursor\.execute)\s*\(\s*(?:f['\"]|['\"].*%s|.*\.format\()''',
         "description": "疑似 SQL 注入（字符串拼接 SQL）"},
        {"name": "shell_injection", "severity": "high",
         "pattern": r'subprocess\.\w+\(.*shell\s*=\s*True',
         "description": "shell=True 可能导致命令注入"},
        {"name": "path_traversal", "severity": "medium",
         "pattern": r'\.\./|\.\.\\\\',
         "description": "路径遍历模式"},
        {"name": "insecure_hash", "severity": "medium",
         "pattern": r'hashlib\.(?:md5|sha1)\(',
         "description": "使用不安全的哈希算法（MD5/SHA1）"},
        {"name": "debug_mode", "severity": "low",
         "pattern": r'debug\s*=\s*True|DEBUG\s*=\s*True',
         "description": "调试模式开启"},
        {"name": "pickle_load", "severity": "medium",
         "pattern": r'pickle\.loads?\(',
         "description": "pickle 反序列化可能导致任意代码执行"},
    ]

    sev_order = {"low": 0, "medium": 1, "high": 2}
    min_sev = sev_order.get(severity, 1)

    findings = []
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb"}

    files_to_scan = []
    if p.is_file():
        files_to_scan = [p]
    else:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        for f in p.rglob("*"):
            if any(part in skip for part in f.relative_to(p).parts):
                continue
            if f.is_file() and f.suffix in code_exts:
                files_to_scan.append(f)
            if len(files_to_scan) >= 200:
                break

    for fp in files_to_scan:
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
            for pat_info in patterns:
                if sev_order.get(pat_info["severity"], 0) < min_sev:
                    continue
                for m in _re.finditer(pat_info["pattern"], content, _re.IGNORECASE):
                    line_num = content[:m.start()].count("\n") + 1
                    findings.append({
                        "file": str(fp.relative_to(p) if p.is_dir() else fp.name),
                        "line": line_num,
                        "rule": pat_info["name"],
                        "severity": pat_info["severity"],
                        "description": pat_info["description"],
                        "match": m.group()[:80],
                    })
        except Exception:
            continue

    return {
        "status": "ok",
        "scanner": "builtin_regex",
        "path": str(p),
        "files_scanned": len(files_to_scan),
        "issues_count": len(findings),
        "issues": findings[:50],
        "severity_filter": severity,
    }
