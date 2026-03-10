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


def _run_quality_cmd(cmd: str, cwd: str = ".", timeout: int = 60) -> dict:
    """执行代码质量工具命令"""
    from turing.config import Config
    cfg = Config.load()
    workspace = cfg.get("security.workspace_root", None) or cwd

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
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
    linter_name, base_cmd = _detect_linter(path)
    if not base_cmd:
        return {"error": "未检测到可用的 linter 工具。请安装 ruff、flake8 或 eslint。"}

    cmd = base_cmd
    if fix and linter_name == "ruff":
        cmd += " --fix"
    elif fix and linter_name == "eslint":
        cmd += " --fix"

    target = path if path != "." else "."
    cmd += f" {target}"

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
    import shutil
    p = Path(path).resolve()

    # 检测格式化工具
    formatter = None
    cmd = None

    # Python
    if shutil.which("ruff") and (p.suffix == ".py" or p.is_dir()):
        formatter = "ruff-format"
        cmd = f"ruff format {'--check' if check_only else ''} {path}"
    elif shutil.which("black") and (p.suffix == ".py" or p.is_dir()):
        formatter = "black"
        cmd = f"black {'--check' if check_only else ''} {path}"

    # JS/TS
    elif shutil.which("npx") and p.suffix in (".js", ".ts", ".jsx", ".tsx", ".json", ".css"):
        formatter = "prettier"
        cmd = f"npx prettier {'--check' if check_only else '--write'} {path}"

    # Go
    elif shutil.which("gofmt") and p.suffix == ".go":
        formatter = "gofmt"
        if check_only:
            cmd = f"gofmt -d {path}"
        else:
            cmd = f"gofmt -w {path}"

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
    import shutil
    p = Path(path).resolve()

    checker = None
    cmd = None

    # Python type checkers
    if p.suffix == ".py" or (p.is_dir() and any(p.glob("**/*.py"))):
        if shutil.which("mypy"):
            checker = "mypy"
            cmd = f"mypy {'--strict' if strict else ''} {path}"
        elif shutil.which("pyright"):
            checker = "pyright"
            cmd = f"pyright {path}"
        else:
            # Try running via python module
            checker = "mypy"
            cmd = f"python3 -m mypy {'--strict' if strict else ''} {path}"

    # TypeScript
    elif p.suffix in (".ts", ".tsx") or (p.is_dir() and (p / "tsconfig.json").exists()):
        checker = "tsc"
        cmd = f"npx tsc --noEmit {'--strict' if strict else ''}"

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
