"""Git 操作工具

为 Turing 补齐 Git 集成能力，提供代码版本管理的完整操作：

读操作（只读，可并行）:
- git_status  — 查看工作区变更状态
- git_diff    — 查看文件 diff（工作区或指定 commit 间）
- git_log     — 查看提交历史
- git_blame   — 查看文件逐行归属

写操作（副作用，顺序执行）:
- git_commit  — 暂存并提交（对标 Aider 的自动提交流）
- git_branch  — 分支管理：创建 / 切换 / 列出分支
- git_stash   — 暂存管理：暂存 / 弹出 / 列出暂存
- git_reset   — 撤销操作：回退最近 N 次提交（对标 Aider /undo）
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
    """查看 Git 仓库状态（分支、修改、暂存、未追踪文件）。"""
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
    """查看差异：工作区/暂存区/提交间对比。"""
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
    """查看提交历史（支持文件过滤和精简模式）。"""
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
    """逐行归因：查看每行代码的作者和提交信息。"""
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


# ===== Git 写操作 =====


@tool(
    name="git_commit",
    description="暂存并提交变更（类似 Aider 自动提交）。默认暂存所有变更文件。",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "提交信息"},
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要暂存的文件列表（默认为空=暂存全部变更）",
            },
            "path": {
                "type": "string",
                "description": "仓库路径（可选，默认当前目录）",
            },
        },
        "required": ["message"],
    },
)
def git_commit(message: str, files: list = None, path: str = ".") -> dict:
    """提交变更（可指定文件或全部暂存）。"""
    # 先暂存
    if files:
        for f in files:
            r = _run_git(["add", "--", f], cwd=path)
            if r.get("exit_code", 1) != 0 and "error" in r:
                return {"error": f"暂存 {f} 失败: {r.get('output', r.get('error', ''))}"}
    else:
        r = _run_git(["add", "-A"], cwd=path)
        if r.get("exit_code", 1) != 0:
            return {"error": f"暂存失败: {r.get('output', r.get('error', ''))}"}

    # 检查是否有变更
    status = _run_git(["diff", "--cached", "--stat"], cwd=path)
    if not status.get("output", "").strip():
        return {"status": "no_changes", "message": "没有可提交的变更"}

    # 提交
    result = _run_git(["commit", "-m", message], cwd=path)
    if result.get("exit_code", 1) != 0:
        return {"error": f"提交失败: {result.get('output', result.get('error', ''))}"}

    # 获取提交信息
    log = _run_git(["log", "-1", "--oneline"], cwd=path)
    return {
        "status": "ok",
        "commit": log.get("output", "").strip(),
        "message": message,
        "files_staged": len(files) if files else "all",
    }


@tool(
    name="git_branch",
    description="分支管理：创建新分支、切换分支、或列出分支。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: create, switch, list（默认 list）",
                "enum": ["create", "switch", "list"],
            },
            "name": {
                "type": "string",
                "description": "分支名（create/switch 时必填）",
            },
            "path": {
                "type": "string",
                "description": "仓库路径（可选）",
            },
        },
        "required": [],
    },
)
def git_branch(action: str = "list", name: str = None, path: str = ".") -> dict:
    """分支管理：list/create/switch/delete。"""
    if action == "list":
        result = _run_git(["branch", "-a"], cwd=path)
        return result

    if not name:
        return {"error": "分支名（name）是必填的"}

    if action == "create":
        result = _run_git(["checkout", "-b", name], cwd=path)
    elif action == "switch":
        result = _run_git(["checkout", name], cwd=path)
    else:
        return {"error": f"不支持的操作: {action}"}

    if result.get("exit_code", 1) != 0:
        return {"error": result.get("output", result.get("error", ""))}
    return {"status": "ok", "action": action, "branch": name}


@tool(
    name="git_stash",
    description="暂存管理：保存当前未提交的变更到暂存栈、弹出暂存、或列出暂存列表。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作: save, pop, list（默认 list）",
                "enum": ["save", "pop", "list"],
            },
            "message": {
                "type": "string",
                "description": "暂存描述信息（save 时可选）",
            },
            "path": {
                "type": "string",
                "description": "仓库路径（可选）",
            },
        },
        "required": [],
    },
)
def git_stash(action: str = "list", message: str = None, path: str = ".") -> dict:
    """暂存/恢复工作区变更。"""
    if action == "save":
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        result = _run_git(args, cwd=path)
    elif action == "pop":
        result = _run_git(["stash", "pop"], cwd=path)
    elif action == "list":
        result = _run_git(["stash", "list"], cwd=path)
    else:
        return {"error": f"不支持的操作: {action}"}

    if result.get("exit_code", 1) != 0 and "error" in result:
        return result
    return {"status": "ok", "action": action, "output": result.get("output", "")}


@tool(
    name="git_reset",
    description="撤销最近的提交（软回退，保留文件变更）。对标 Aider 的 /undo 功能。",
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "回退几个提交（默认 1）",
            },
            "hard": {
                "type": "boolean",
                "description": "是否硬回退（丢弃变更，默认 false=软回退保留文件变更）",
            },
            "path": {
                "type": "string",
                "description": "仓库路径（可选）",
            },
        },
        "required": [],
    },
)
def git_reset(count: int = 1, hard: bool = False, path: str = ".") -> dict:
    """回退提交（支持 soft/hard 模式）。"""
    # 先记录当前 HEAD 用于报告
    before = _run_git(["log", "-1", "--oneline"], cwd=path)

    mode = "--hard" if hard else "--soft"
    result = _run_git(["reset", mode, f"HEAD~{count}"], cwd=path)
    if result.get("exit_code", 1) != 0:
        return {"error": result.get("output", result.get("error", ""))}

    after = _run_git(["log", "-1", "--oneline"], cwd=path)
    return {
        "status": "ok",
        "mode": "hard" if hard else "soft",
        "rolled_back": count,
        "before": before.get("output", "").strip(),
        "now_at": after.get("output", "").strip(),
    }


# ────────────────── PR 摘要工具 ──────────────────


@tool(
    name="pr_summary",
    description="基于 git diff 自动生成 Pull Request 描述：变更摘要、"
                "修改文件列表、影响范围和测试建议。",
    parameters={
        "type": "object",
        "properties": {
            "base_branch": {
                "type": "string",
                "description": "基础分支（默认 main）",
            },
            "path": {
                "type": "string",
                "description": "仓库路径（可选）",
            },
        },
        "required": [],
    },
)
def pr_summary(base_branch: str = "main", path: str = ".") -> dict:
    """生成 PR 摘要描述。"""
    import re as _re

    # 获取当前分支名
    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    current_branch = branch_result.get("output", "").strip()

    # 获取 diff stat
    stat_result = _run_git(["diff", "--stat", f"{base_branch}...HEAD"], cwd=path)
    stat_output = stat_result.get("output", "")

    # 获取 diff 内容（限制大小）
    diff_result = _run_git(["diff", "--no-color", f"{base_branch}...HEAD"], cwd=path)
    diff_output = diff_result.get("output", "")

    # 获取提交列表
    log_result = _run_git(
        ["log", "--oneline", f"{base_branch}..HEAD"], cwd=path
    )
    commits = [
        line.strip()
        for line in log_result.get("output", "").strip().split("\n")
        if line.strip()
    ]

    # 解析变更文件
    files_changed = []
    additions = 0
    deletions = 0
    for line in stat_output.strip().split("\n"):
        m = _re.match(r'\s*(.+?)\s*\|\s*(\d+)', line)
        if m:
            files_changed.append(m.group(1).strip())
        # 最后一行是统计总计
        m_total = _re.match(r'\s*(\d+)\s+files?\s+changed(?:,\s*(\d+)\s+insertion)?(?:.*?(\d+)\s+deletion)?', line)
        if m_total:
            additions = int(m_total.group(2) or 0)
            deletions = int(m_total.group(3) or 0)

    # 分类文件
    file_categories = {}
    for f in files_changed:
        if "test" in f.lower():
            file_categories.setdefault("tests", []).append(f)
        elif f.endswith((".md", ".txt", ".rst")):
            file_categories.setdefault("docs", []).append(f)
        elif f.endswith((".yml", ".yaml", ".json", ".toml", ".cfg")):
            file_categories.setdefault("config", []).append(f)
        else:
            file_categories.setdefault("source", []).append(f)

    # 生成描述
    change_scope = "minor" if additions + deletions < 50 else "moderate" if additions + deletions < 200 else "major"

    suggestions = []
    if not file_categories.get("tests"):
        suggestions.append("建议：添加或更新测试覆盖本次变更")
    if change_scope == "major":
        suggestions.append("注意：变更幅度较大，建议分阶段 review")

    return {
        "status": "ok",
        "current_branch": current_branch,
        "base_branch": base_branch,
        "commits": commits[:20],
        "commit_count": len(commits),
        "files_changed": files_changed,
        "file_count": len(files_changed),
        "additions": additions,
        "deletions": deletions,
        "change_scope": change_scope,
        "file_categories": file_categories,
        "suggestions": suggestions,
        "diff_preview": diff_output[:3000] if diff_output else "",
    }
