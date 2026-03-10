"""文件操作工具

提供三个文件操作原语：
- read_file  — 读取文件内容（支持行号范围）
- write_file — 创建 / 覆盖文件
- edit_file  — 精确字符串替换编辑

安全约束：
- 所有操作均经过 ``_check_path_security()`` 的路径黑名单检查
- 被禁止的路径在 config.yaml 中的 security.blocked_paths 配置
"""

from __future__ import annotations

import os
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
    err = _check_path_security(path)
    if err:
        return {"error": err}
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": str(p), "bytes": len(content.encode("utf-8"))}
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

        p.write_text(new_text, encoding="utf-8")
        return {"status": "ok", "path": str(p), "replacements": 1}
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
    gen_dir = _get_generated_code_dir()
    # 防止路径逃逸
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        return {"error": "路径不合法：不能使用绝对路径或 .. 逃逸"}
    full_path = os.path.join(gen_dir, normalized)
    return write_file(full_path, content)
