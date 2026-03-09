"""多文件重构工具

为 Turing 补齐多文件编辑能力（对标 Codex 的批量修改和符号重命名）：
- batch_edit     — 在多个文件中应用批量编辑（搜索替换 / 插入 / 删除）
- rename_symbol  — 跨项目搜索并安全替换符号名（函数、类、变量名等）

Codex 和 Claude Opus 都能自信地进行跨文件重构。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from turing.tools.registry import tool


@tool(
    name="batch_edit",
    description="在多个文件中批量执行搜索替换。支持正则表达式。可用于跨文件重构、批量修改配置等。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要搜索的文本或正则表达式",
            },
            "replacement": {
                "type": "string",
                "description": "替换为的文本（支持正则反向引用如 \\1）",
            },
            "file_pattern": {
                "type": "string",
                "description": "文件路径 glob 模式（如 '**/*.py' 或 'src/**/*.ts'）",
            },
            "path": {
                "type": "string",
                "description": "搜索根目录（默认当前目录）",
            },
            "is_regex": {
                "type": "boolean",
                "description": "pattern 是否为正则表达式（默认 false）",
            },
            "dry_run": {
                "type": "boolean",
                "description": "仅预览不实际修改（默认 true，安全优先）",
            },
        },
        "required": ["pattern", "replacement", "file_pattern"],
    },
)
def batch_edit(
    pattern: str,
    replacement: str,
    file_pattern: str,
    path: str = ".",
    is_regex: bool = False,
    dry_run: bool = True,
) -> dict:
    from turing.config import Config
    cfg = Config.load()
    workspace = cfg.get("security.workspace_root", None) or path
    p = Path(workspace).resolve()

    if not p.is_dir():
        return {"error": f"路径不存在: {path}"}

    # 安全检查：避免超大替换
    matched_files = list(p.glob(file_pattern))
    # 排除隐藏目录和 node_modules 等
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    matched_files = [
        f for f in matched_files
        if f.is_file() and not any(part in skip_dirs for part in f.parts)
    ]

    if len(matched_files) > 500:
        return {"error": f"匹配文件过多（{len(matched_files)}），请缩小范围。"}

    results = {
        "total_files_scanned": len(matched_files),
        "files_with_matches": 0,
        "total_replacements": 0,
        "changes": [],
        "dry_run": dry_run,
    }

    for filepath in matched_files:
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        if is_regex:
            matches = list(re.finditer(pattern, content))
            if not matches:
                continue
            new_content = re.sub(pattern, replacement, content)
            match_count = len(matches)
        else:
            count = content.count(pattern)
            if count == 0:
                continue
            new_content = content.replace(pattern, replacement)
            match_count = count

        rel_path = str(filepath.relative_to(p))
        results["files_with_matches"] += 1
        results["total_replacements"] += match_count
        results["changes"].append({
            "file": rel_path,
            "matches": match_count,
        })

        if not dry_run:
            filepath.write_text(new_content, encoding="utf-8")

    # 限制输出大小
    if len(results["changes"]) > 50:
        results["changes"] = results["changes"][:50]
        results["changes_truncated"] = True

    return results


@tool(
    name="rename_symbol",
    description="跨项目安全重命名符号（函数名、类名、变量名等）。使用词边界匹配避免误替换。默认 dry_run 预览。",
    parameters={
        "type": "object",
        "properties": {
            "old_name": {
                "type": "string",
                "description": "原始符号名",
            },
            "new_name": {
                "type": "string",
                "description": "新符号名",
            },
            "file_pattern": {
                "type": "string",
                "description": "文件路径 glob 模式（如 '**/*.py'）",
            },
            "path": {
                "type": "string",
                "description": "搜索根目录（默认当前目录）",
            },
            "dry_run": {
                "type": "boolean",
                "description": "仅预览不实际修改（默认 true）",
            },
        },
        "required": ["old_name", "new_name", "file_pattern"],
    },
)
def rename_symbol(
    old_name: str,
    new_name: str,
    file_pattern: str,
    path: str = ".",
    dry_run: bool = True,
) -> dict:
    # 使用词边界匹配，只替换完整符号
    # 确保不误替换更长的名称如 old_name_extra
    pattern = r"\b" + re.escape(old_name) + r"\b"

    from turing.config import Config
    cfg = Config.load()
    workspace = cfg.get("security.workspace_root", None) or path
    p = Path(workspace).resolve()

    if not p.is_dir():
        return {"error": f"路径不存在: {path}"}

    # 验证新旧名称
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", old_name):
        return {"error": f"旧名称 '{old_name}' 不是有效的标识符"}
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", new_name):
        return {"error": f"新名称 '{new_name}' 不是有效的标识符"}

    matched_files = list(p.glob(file_pattern))
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    matched_files = [
        f for f in matched_files
        if f.is_file() and not any(part in skip_dirs for part in f.parts)
    ]

    results = {
        "old_name": old_name,
        "new_name": new_name,
        "total_files_scanned": len(matched_files),
        "files_with_matches": 0,
        "total_replacements": 0,
        "changes": [],
        "dry_run": dry_run,
    }

    for filepath in matched_files:
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        matches = list(re.finditer(pattern, content))
        if not matches:
            continue

        new_content = re.sub(pattern, new_name, content)
        rel_path = str(filepath.relative_to(p))
        results["files_with_matches"] += 1
        results["total_replacements"] += len(matches)

        # 提供上下文预览（前2个匹配的行）
        preview_lines = []
        lines = content.splitlines()
        shown = 0
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line) and shown < 2:
                preview_lines.append(f"L{i}: {line.strip()}")
                shown += 1

        results["changes"].append({
            "file": rel_path,
            "matches": len(matches),
            "preview": preview_lines,
        })

        if not dry_run:
            filepath.write_text(new_content, encoding="utf-8")

    if len(results["changes"]) > 30:
        results["changes"] = results["changes"][:30]
        results["changes_truncated"] = True

    return results
