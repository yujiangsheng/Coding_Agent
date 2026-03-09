"""搜索工具

- search_code — 在代码库中搜索文本 / 正则（优先使用 ripgrep，回退 grep）
- list_directory — 列出目录内容
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from turing.tools.registry import tool


@tool(
    name="search_code",
    description="在代码库中搜索文本或正则表达式，返回匹配的文件和行。可指定上下文行数和最大结果数。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索内容"},
            "path": {
                "type": "string",
                "description": "搜索的目录路径（可选，默认当前目录）",
            },
            "is_regex": {
                "type": "boolean",
                "description": "是否为正则表达式（默认 false）",
            },
            "context_lines": {
                "type": "integer",
                "description": "每个匹配前后显示的上下文行数（默认 0）",
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数（默认 50，最大 200）",
            },
            "file_pattern": {
                "type": "string",
                "description": "限定搜索的文件模式（如 '*.py' 或 '*.ts'）",
            },
        },
        "required": ["query"],
    },
)
def search_code(
    query: str, path: str = ".", is_regex: bool = False,
    context_lines: int = 0, max_results: int = 50,
    file_pattern: str = None,
) -> dict:
    try:
        search_dir = Path(path).resolve()
        if not search_dir.exists():
            return {"error": f"目录不存在: {path}"}

        max_results = min(max_results, 200)

        # 优先使用 ripgrep
        rg = _which("rg")
        if rg:
            cmd = [rg, "--no-heading", "--line-number",
                   "--max-count", str(max_results)]
            if context_lines > 0:
                cmd.extend(["-C", str(min(context_lines, 5))])
            if not is_regex:
                cmd.append("--fixed-strings")
            if file_pattern:
                cmd.extend(["-g", file_pattern])
            cmd.extend([query, str(search_dir)])
        else:
            cmd = ["grep", "-rn", f"--max-count={max_results}"]
            if context_lines > 0:
                cmd.append(f"-C{min(context_lines, 5)}")
            if not is_regex:
                cmd.append("-F")
            if file_pattern:
                cmd.extend(["--include", file_pattern])
            cmd.extend([query, str(search_dir)])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )

        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            matches.append(line)
            if len(matches) >= max_results * (1 + context_lines * 2):
                break

        return {"matches": matches, "count": len(matches), "truncated": len(matches) >= max_results}
    except subprocess.TimeoutExpired:
        return {"error": "搜索超时"}
    except Exception as ex:
        return {"error": f"搜索失败: {ex}"}


@tool(
    name="list_directory",
    description="列出目录中的文件和子目录。可递归列出并显示文件大小。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径（默认当前目录）",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归列出子目录（默认 false）",
            },
            "max_depth": {
                "type": "integer",
                "description": "递归最大深度（默认 3）",
            },
            "show_size": {
                "type": "boolean",
                "description": "是否显示文件大小（默认 false）",
            },
        },
        "required": ["path"],
    },
)
def list_directory(
    path: str = ".", recursive: bool = False, max_depth: int = 3,
    show_size: bool = False,
) -> dict:
    try:
        p = Path(path).resolve()
        if not p.exists():
            return {"error": f"目录不存在: {path}"}
        if not p.is_dir():
            return {"error": f"不是目录: {path}"}

        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox"}

        def _list(directory: Path, depth: int) -> list:
            items = []
            try:
                for item in sorted(directory.iterdir()):
                    if item.name in skip_dirs:
                        continue
                    if item.is_dir():
                        entry = {"name": item.name + "/", "type": "dir"}
                        if recursive and depth < max_depth:
                            entry["children"] = _list(item, depth + 1)
                        items.append(entry)
                    else:
                        entry = {"name": item.name, "type": "file"}
                        if show_size:
                            try:
                                entry["size"] = item.stat().st_size
                            except OSError:
                                entry["size"] = -1
                        items.append(entry)
                    if len(items) >= 500:
                        break
            except PermissionError:
                pass
            return items

        if recursive:
            tree = _list(p, 0)
            return {"path": str(p), "tree": tree, "recursive": True}
        else:
            entries = []
            for item in sorted(p.iterdir()):
                name = item.name
                if item.is_dir():
                    name += "/"
                entry = name
                if show_size and item.is_file():
                    try:
                        entry = f"{name} ({item.stat().st_size} bytes)"
                    except OSError:
                        pass
                entries.append(entry)
            return {"path": str(p), "entries": entries, "count": len(entries)}

    except PermissionError:
        return {"error": f"无权限访问: {path}"}
    except Exception as ex:
        return {"error": f"列目录失败: {ex}"}


def _which(cmd: str) -> str | None:
    """检查命令是否存在"""
    import shutil
    return shutil.which(cmd)
