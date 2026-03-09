"""Git 操作工具

为 Turing 补齐 Git 集成能力，提供代码版本管理的基础操作：
- git_status  — 查看工作区变更状态
- git_diff    — 查看文件 diff（工作区或指定 commit 间）
- git_log     — 查看提交历史
- git_blame   — 查看文件逐行归属

这些工具是 Claude Opus / Copilot 等顶尖编码智能体的标配能力。
"""

from __future__ import annotations

import subprocess

from turing.tools.registry import tool


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 15) -> dict:
    """安全执行 git 命令"""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr and result.returncode != 0:
            output += "\n" + result.stderr
        if len(output) > 50000:
            output = output[:25000] + "\n...(输出截断)...\n" + output[-25000:]
        return {"exit_code": result.returncode, "output": output.strip()}
    except FileNotFoundError:
        return {"error": "git 未安装"}
    except subprocess.TimeoutExpired:
        return {"error": f"git 命令超时（>{timeout}s）"}
    except Exception as e:
        return {"error": f"git 执行失败: {e}"}


@tool(
    name="git_status",
    description="查看当前 Git 仓库的工作区状态（修改、暂存、未跟踪文件）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径（可选，默认当前目录）",
            },
        },
        "required": [],
    },
)
def git_status(path: str = ".") -> dict:
    return _run_git(["status", "--short", "--branch"], cwd=path)


@tool(
    name="git_diff",
    description="查看 Git diff。可查看工作区变更、暂存区变更，或指定 commit 之间的差异。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径（可选，默认当前目录）",
            },
            "file": {
                "type": "string",
                "description": "指定文件路径（可选，默认全部）",
            },
            "staged": {
                "type": "boolean",
                "description": "是否查看暂存区 diff（默认 false，查看工作区）",
            },
            "commit": {
                "type": "string",
                "description": "指定 commit 或范围，如 HEAD~3 或 abc123..def456",
            },
        },
        "required": [],
    },
)
def git_diff(
    path: str = ".",
    file: str = None,
    staged: bool = False,
    commit: str = None,
) -> dict:
    args = ["diff"]
    if staged:
        args.append("--cached")
    if commit:
        args.append(commit)
    args.append("--")
    if file:
        args.append(file)
    return _run_git(args, cwd=path)


@tool(
    name="git_log",
    description="查看 Git 提交历史。支持指定条数和文件过滤。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "仓库路径（可选，默认当前目录）",
            },
            "count": {
                "type": "integer",
                "description": "显示最近 N 条提交（默认 10）",
            },
            "file": {
                "type": "string",
                "description": "仅显示涉及指定文件的提交",
            },
            "oneline": {
                "type": "boolean",
                "description": "是否使用精简单行格式（默认 true）",
            },
        },
        "required": [],
    },
)
def git_log(
    path: str = ".",
    count: int = 10,
    file: str = None,
    oneline: bool = True,
) -> dict:
    args = ["log", f"-{count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%H %ai %an%n  %s"])
    if file:
        args.extend(["--", file])
    return _run_git(args, cwd=path)


@tool(
    name="git_blame",
    description="查看文件的逐行 Git blame 信息（谁在什么时候改了哪一行）。",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "文件路径"},
            "start_line": {
                "type": "integer",
                "description": "起始行号（可选）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（可选）",
            },
        },
        "required": ["file"],
    },
)
def git_blame(file: str, start_line: int = None, end_line: int = None) -> dict:
    args = ["blame", "--line-porcelain"]
    if start_line and end_line:
        args.extend([f"-L{start_line},{end_line}"])
    elif start_line:
        args.extend([f"-L{start_line},+20"])
    args.append(file)
    result = _run_git(args)
    if "error" in result:
        return result
    # 简化 porcelain 输出为更易读的格式
    lines = result.get("output", "").split("\n")
    simplified = []
    current = {}
    for line in lines:
        if line.startswith("\t"):
            current["code"] = line[1:]
            simplified.append(current)
            current = {}
        elif line.startswith("author "):
            current["author"] = line[7:]
        elif line.startswith("committer-time "):
            pass
        elif line.startswith("summary "):
            current["summary"] = line[8:]
        elif " " in line and len(line.split()[0]) >= 7:
            parts = line.split()
            if len(parts) >= 3:
                current["commit"] = parts[0][:8]
                current["line"] = parts[2] if len(parts) > 2 else ""
    if simplified:
        return {"blame": simplified[:100], "count": len(simplified)}
    return result
