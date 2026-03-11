"""文件操作工具（v2.0 — 完整文件管理）

提供完整的文件操作原语（对标 Claude Code / Cursor 的文件管理能力）：
- read_file     — 读取文件内容（支持行号范围）
- write_file    — 创建 / 覆盖文件
- edit_file     — 精确字符串替换编辑
- generate_file — 在 generated_code 目录下创建文件
- multi_edit    — 原子化多文件编辑（v2.0 新增）
- move_file     — 移动/重命名文件（v2.0 新增）
- copy_file     — 复制文件或目录（v2.0 新增）
- delete_file   — 删除文件或空目录（v2.0 新增）
- find_files    — 按模式搜索文件（v2.0 新增）

安全约束：
- 所有操作均经过 ``_check_path_security()`` 的路径黑名单检查
- 被禁止的路径在 config.yaml 中的 security.blocked_paths 配置
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import shutil
from pathlib import Path

from turing.tools.registry import tool


def _get_generated_code_dir() -> str:
    """获取生成代码的输出目录"""
    from turing.config import Config
    cfg = Config.load()
    return cfg.get("output.generated_code_dir", "generated_code")


def _check_path_security(path: str) -> str | None:
    """路径安全检查，返回错误信息或 None"""
    from turing.config import Config
    cfg = Config.load()
    blocked = cfg.get("security.blocked_paths", [])
    resolved = str(Path(path).resolve())
    for bp in blocked:
        if resolved.startswith(str(Path(bp).resolve())):
            return f"安全限制：禁止访问 {path}"
    return None


@tool(
    name="read_file",
    description="读取文件内容。可指定行号范围读取部分内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "start_line": {
                "type": "integer",
                "description": "起始行号（从1开始，可选）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含，可选）",
            },
        },
        "required": ["path"],
    },
)
def read_file(path: str, start_line: int = None, end_line: int = None) -> dict:
    """读取文件内容，可指定行号范围。"""
    err = _check_path_security(path)
    if err:
        return {"error": err}
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"文件不存在: {path}"}
        if not p.is_file():
            return {"error": f"不是文件: {path}"}

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        s = (start_line or 1) - 1
        e = end_line or total
        s = max(0, s)
        e = min(total, e)
        selected = lines[s:e]

        return {
            "content": "".join(selected),
            "total_lines": total,
            "range": f"{s + 1}-{e}",
        }
    except Exception as ex:
        return {"error": f"读取文件失败: {ex}"}


@tool(
    name="write_file",
    description="创建或覆盖文件，写入指定内容。目录不存在会自动创建。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> dict:
    """创建或覆盖文件，自动创建目录，已有文件返回 diff 预览。"""
    err = _check_path_security(path)
    if err:
        return {"error": err}
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # 如果文件已存在，生成 diff 预览
        diff_str = ""
        if p.exists():
            try:
                old_text = p.read_text(encoding="utf-8", errors="replace")
                old_lines = old_text.splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)
                diff = list(difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=f"a/{path}", tofile=f"b/{path}",
                    n=3,
                ))
                diff_str = "".join(diff[:80])
            except Exception:
                pass

        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        result = {"status": "ok", "path": str(p), "bytes": len(content.encode("utf-8"))}
        if diff_str:
            result["diff"] = diff_str
        return result
    except Exception as ex:
        return {"error": f"写入文件失败: {ex}"}


@tool(
    name="edit_file",
    description="编辑文件：将文件中的 old_str 替换为 new_str。old_str 必须精确匹配。如果匹配多处，可用 occurrence 指定替换第几处（从1开始）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_str": {"type": "string", "description": "要替换的原始文本"},
            "new_str": {"type": "string", "description": "替换后的文本"},
            "occurrence": {
                "type": "integer",
                "description": "当 old_str 匹配多处时，指定替换第几处（从1开始，默认要求唯一匹配）",
            },
        },
        "required": ["path", "old_str", "new_str"],
    },
)
def edit_file(path: str, old_str: str, new_str: str, occurrence: int = 0) -> dict:
    """精确替换编辑：匹配 old_str 并替换为 new_str，返回 diff 预览。"""
    err = _check_path_security(path)
    if err:
        return {"error": err}
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"文件不存在: {path}"}

        text = p.read_text(encoding="utf-8")
        count = text.count(old_str)
        if count == 0:
            # 提示近似匹配帮助调试
            stripped = old_str.strip()
            if stripped and stripped in text:
                return {"error": "未找到 old_str（完全匹配），但去除首尾空白后可匹配——请检查缩进和换行"}
            return {"error": "未找到 old_str，请确认内容完全匹配（包括空格和换行）"}

        if count > 1 and occurrence == 0:
            # 给出每处匹配的行号，帮助用户定位
            lines = text.split("\n")
            locations = []
            search_start = 0
            for i in range(count):
                pos = text.index(old_str, search_start)
                line_no = text[:pos].count("\n") + 1
                locations.append(line_no)
                search_start = pos + 1
            return {
                "error": f"old_str 匹配了 {count} 处（行 {locations}），请添加更多上下文使其唯一，或指定 occurrence 参数"
            }

        if occurrence > 0:
            # 替换第 N 次出现
            if occurrence > count:
                return {"error": f"occurrence={occurrence} 但只有 {count} 处匹配"}
            idx = -1
            for _ in range(occurrence):
                idx = text.index(old_str, idx + 1)
            new_text = text[:idx] + new_str + text[idx + len(old_str):]
        else:
            new_text = text.replace(old_str, new_str, 1)

        # 生成 unified diff 预览（对标 Aider/Cursor 的 diff 可视化）
        old_lines = text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}",
            n=3,
        ))
        diff_str = "".join(diff[:80])  # 上限 80 行避免过长

        p.write_text(new_text, encoding="utf-8")
        return {
            "status": "ok",
            "path": str(p),
            "replacements": 1,
            "diff": diff_str,
        }
    except Exception as ex:
        return {"error": f"编辑文件失败: {ex}"}


@tool(
    name="generate_file",
    description="在 generated_code 目录下创建文件。路径相对于 generated_code 目录，目录结构会自动创建。用于生成新代码文件。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于 generated_code 目录的文件路径，例如 'my_project/src/main.py'",
            },
            "content": {"type": "string", "description": "文件内容"},
        },
        "required": ["path", "content"],
    },
)
def generate_file(path: str, content: str) -> dict:
    """生成新文件，已存在时返回确认提示。"""
    gen_dir = _get_generated_code_dir()
    # 防止路径逃逸
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        return {"error": "路径不合法：不能使用绝对路径或 .. 逃逸"}
    full_path = os.path.join(gen_dir, normalized)
    return write_file(full_path, content)


# ── v2.0 新增：完整文件管理工具 ──────────────────────────


@tool(
    name="multi_edit",
    description="原子化多文件编辑：接受多组 {path, old_str, new_str} 编辑操作，全部成功才保存，任一失败则全部回滚。适合跨文件重构。",
    parameters={
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "description": "编辑操作列表，每项包含 path、old_str、new_str",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_str": {"type": "string"},
                        "new_str": {"type": "string"},
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            },
        },
        "required": ["edits"],
    },
)
def multi_edit(edits: list) -> dict:
    """原子化多文件编辑：按顺序执行编辑，任意一步失败则全部回滚。"""
    if not edits:
        return {"error": "编辑列表为空"}

    # Phase 1: 验证所有编辑（不修改文件）
    originals = {}  # path → original_text
    planned = []     # (path, old_text, new_text)

    for i, edit in enumerate(edits):
        p_str = edit.get("path", "")
        old_str = edit.get("old_str", "")
        new_str = edit.get("new_str", "")

        err = _check_path_security(p_str)
        if err:
            return {"error": f"编辑 #{i + 1}: {err}"}

        p = Path(p_str)
        if not p.exists():
            return {"error": f"编辑 #{i + 1}: 文件不存在: {p_str}"}

        # 第一次读取时记录原始内容
        if p_str not in originals:
            originals[p_str] = p.read_text(encoding="utf-8")

        text = originals[p_str]
        # 应用之前对同文件的编辑
        for pp, po, pn in planned:
            if pp == p_str:
                text = text.replace(po, pn, 1)

        if old_str not in text:
            return {"error": f"编辑 #{i + 1}: 在 {p_str} 中未找到 old_str"}

        planned.append((p_str, old_str, new_str))

    # Phase 2: 全部验证通过，执行所有编辑
    results = []
    modified_files = {}  # path → final_text
    for p_str, old_str, new_str in planned:
        text = modified_files.get(p_str, originals[p_str])
        text = text.replace(old_str, new_str, 1)
        modified_files[p_str] = text

    try:
        for p_str, new_text in modified_files.items():
            Path(p_str).write_text(new_text, encoding="utf-8")
            results.append({"path": p_str, "status": "ok"})
    except Exception as ex:
        # 回滚已写入的文件
        for p_str, orig_text in originals.items():
            try:
                Path(p_str).write_text(orig_text, encoding="utf-8")
            except Exception:
                pass
        return {"error": f"写入失败并已回滚: {ex}", "rollback": True}

    return {"status": "ok", "files_modified": len(modified_files), "edits_applied": len(planned), "results": results}


@tool(
    name="move_file",
    description="移动或重命名文件/目录。",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源路径"},
            "destination": {"type": "string", "description": "目标路径"},
        },
        "required": ["source", "destination"],
    },
)
def move_file(source: str, destination: str) -> dict:
    """移动或重命名文件/目录。"""
    for p in [source, destination]:
        err = _check_path_security(p)
        if err:
            return {"error": err}

    src = Path(source)
    if not src.exists():
        return {"error": f"源文件不存在: {source}"}

    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(src), str(dst))
        return {"status": "ok", "source": source, "destination": str(dst)}
    except Exception as ex:
        return {"error": f"移动文件失败: {ex}"}


@tool(
    name="copy_file",
    description="复制文件或目录。目录递归复制。",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源路径"},
            "destination": {"type": "string", "description": "目标路径"},
        },
        "required": ["source", "destination"],
    },
)
def copy_file(source: str, destination: str) -> dict:
    """复制文件或目录。"""
    for p in [source, destination]:
        err = _check_path_security(p)
        if err:
            return {"error": err}

    src = Path(source)
    if not src.exists():
        return {"error": f"源文件不存在: {source}"}

    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return {"status": "ok", "source": source, "destination": str(dst)}
    except Exception as ex:
        return {"error": f"复制文件失败: {ex}"}


@tool(
    name="delete_file",
    description="删除文件或空目录。不支持递归删除非空目录（安全措施）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要删除的文件/目录路径"},
        },
        "required": ["path"],
    },
)
def delete_file(path: str) -> dict:
    """安全删除文件（非空目录默认拒绝）。"""
    err = _check_path_security(path)
    if err:
        return {"error": err}

    p = Path(path)
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    try:
        if p.is_file() or p.is_symlink():
            p.unlink()
        elif p.is_dir():
            if any(p.iterdir()):
                return {"error": "安全限制：不允许删除非空目录，请先清空内容"}
            p.rmdir()
        return {"status": "ok", "path": path}
    except Exception as ex:
        return {"error": f"删除失败: {ex}"}


@tool(
    name="find_files",
    description="按 glob 模式搜索文件。支持 *.py、**/*.js 等模式。返回匹配的文件路径列表。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式，支持 *, ?, ** 通配符（如 '*.py', '**/*.test.js'）",
            },
            "path": {
                "type": "string",
                "description": "搜索起始目录（默认 workspace_root）",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回数量（默认 100）",
            },
        },
        "required": ["pattern"],
    },
)
def find_files(pattern: str, path: str = None, max_results: int = 100) -> dict:
    """按名称模式搜索文件（glob），可选内容正则匹配。"""
    from turing.config import Config
    cfg = Config.load()
    root = path or cfg.get("security.workspace_root", None) or "."

    err = _check_path_security(root)
    if err:
        return {"error": err}

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        return {"error": f"目录不存在: {root}"}

    matches = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox"}

    for dirpath, dirnames, filenames in os.walk(root_path):
        # 跳过常见的无关目录
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if fnmatch.fnmatch(fname, pattern):
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root_path)
                matches.append(rel)
                if len(matches) >= max_results:
                    return {"files": matches, "count": len(matches), "truncated": True}

    return {"files": matches, "count": len(matches), "truncated": False}
