"""AST 智能代码分析工具

提供基于 Python AST 的深度代码理解能力（对标 Gemini/Codex 的代码分析能力）：
- code_structure    — 提取文件的类、函数、导入等结构信息
- call_graph        — 分析函数调用关系图
- complexity_report — 计算代码复杂度并识别热点
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path

from turing.tools.registry import tool


def _safe_parse(filepath: Path) -> ast.Module | None:
    """安全地解析 Python 文件，失败返回 None"""
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        return ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return None


@tool(
    name="code_structure",
    description="解析 Python 文件的 AST，提取类、函数、全局变量、导入等结构信息。"
                "可用于快速理解文件组织结构，无需逐行阅读。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Python 文件或目录路径",
            },
            "include_private": {
                "type": "boolean",
                "description": "是否包含以 _ 开头的私有成员（默认 false）",
            },
        },
        "required": ["path"],
    },
)
def code_structure(path: str, include_private: bool = False) -> dict:
    """提取 Python 文件 / 目录的代码结构"""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    if p.is_file():
        if not p.suffix == ".py":
            return {"error": "仅支持 Python 文件"}
        return _extract_structure(p, include_private)

    # 目录模式：汇总所有 py 文件
    results = {}
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    py_files = sorted(
        f for f in p.rglob("*.py")
        if not any(part in skip for part in f.relative_to(p).parts)
    )
    if len(py_files) > 100:
        py_files = py_files[:100]

    for fp in py_files:
        rel = str(fp.relative_to(p))
        info = _extract_structure(fp, include_private)
        if info.get("classes") or info.get("functions") or info.get("global_vars"):
            results[rel] = info

    return {
        "directory": str(p),
        "total_files": len(py_files),
        "files_with_content": len(results),
        "structure": results,
    }


def _extract_structure(filepath: Path, include_private: bool) -> dict:
    """从单个文件提取结构"""
    tree = _safe_parse(filepath)
    if tree is None:
        return {"error": "解析失败（语法错误）"}

    classes = []
    functions = []
    imports = []
    global_vars = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            if not include_private and node.name.startswith("_"):
                continue
            cls_info = {
                "name": node.name,
                "line": node.lineno,
                "bases": [_name_of(b) for b in node.bases],
                "methods": [],
                "decorators": [_name_of(d) for d in node.decorator_list],
            }
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not include_private and item.name.startswith("_") and item.name != "__init__":
                        continue
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    cls_info["methods"].append({
                        "name": item.name,
                        "line": item.lineno,
                        "args": args,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                    })
            classes.append(cls_info)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not include_private and node.name.startswith("_"):
                continue
            args = [a.arg for a in node.args.args]
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "args": args,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "decorators": [_name_of(d) for d in node.decorator_list],
            })

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            else:
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                name = _name_of(target)
                if name and (include_private or not name.startswith("_")):
                    global_vars.append({"name": name, "line": node.lineno})

    total_lines = len(filepath.read_text(encoding="utf-8", errors="ignore").splitlines())

    return {
        "file": str(filepath),
        "total_lines": total_lines,
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "global_vars": global_vars,
    }


@tool(
    name="call_graph",
    description="分析 Python 文件 / 目录的函数调用关系图。"
                "识别哪些函数调用了哪些函数，帮助理解代码执行流程和依赖关系。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Python 文件或目录路径",
            },
            "target_function": {
                "type": "string",
                "description": "聚焦分析某个函数的调用者和被调用者（可选）",
            },
        },
        "required": ["path"],
    },
)
def call_graph(path: str, target_function: str = None) -> dict:
    """构建函数调用关系图"""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    # 收集所有 py 文件
    if p.is_file():
        py_files = [p] if p.suffix == ".py" else []
    else:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        py_files = sorted(
            f for f in p.rglob("*.py")
            if not any(part in skip for part in f.relative_to(p).parts)
        )[:80]

    if not py_files:
        return {"error": "未找到 Python 文件"}

    base = p if p.is_dir() else p.parent

    # 第一遍：收集所有定义
    all_defs = {}  # name -> {file, line, type}
    for fp in py_files:
        tree = _safe_parse(fp)
        if not tree:
            continue
        rel = str(fp.relative_to(base)) if fp != base else fp.name
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_defs[node.name] = {"file": rel, "line": node.lineno, "type": "function"}
            elif isinstance(node, ast.ClassDef):
                all_defs[node.name] = {"file": rel, "line": node.lineno, "type": "class"}

    # 第二遍：收集调用关系
    calls = defaultdict(set)   # caller -> {callees}
    callers = defaultdict(set)  # callee -> {callers}

    for fp in py_files:
        tree = _safe_parse(fp)
        if not tree:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = node.name
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee = _call_name(child)
                        if callee and callee in all_defs and callee != caller:
                            calls[caller].add(callee)
                            callers[callee].add(caller)

    # 如果聚焦某个函数
    if target_function:
        if target_function not in all_defs:
            return {"error": f"未找到函数 '{target_function}'"}
        return {
            "target": target_function,
            "definition": all_defs[target_function],
            "calls": sorted(calls.get(target_function, set())),
            "called_by": sorted(callers.get(target_function, set())),
        }

    # 构建完整图
    graph = {}
    for func_name in sorted(all_defs.keys()):
        if func_name in calls or func_name in callers:
            graph[func_name] = {
                "defined_in": all_defs[func_name]["file"],
                "calls": sorted(calls.get(func_name, set())),
                "called_by": sorted(callers.get(func_name, set())),
            }

    # 识别入口点（被调用但不调用别人，或 main 等）
    entry_points = [
        name for name, info in graph.items()
        if not info["called_by"] and info["calls"]
    ]

    # 识别热点（被最多函数调用）
    hotspots = sorted(
        [(name, len(info["called_by"])) for name, info in graph.items() if info["called_by"]],
        key=lambda x: -x[1]
    )[:10]

    return {
        "total_definitions": len(all_defs),
        "total_call_edges": sum(len(v) for v in calls.values()),
        "entry_points": entry_points[:20],
        "hotspots": [{"name": n, "caller_count": c} for n, c in hotspots],
        "graph": dict(list(graph.items())[:50]),  # 限制输出
    }


@tool(
    name="complexity_report",
    description="计算 Python 代码的圈复杂度和认知复杂度，识别需要重构的高复杂度函数。"
                "高复杂度函数是 bug 密集区，应优先重构。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Python 文件或目录路径",
            },
            "threshold": {
                "type": "integer",
                "description": "高复杂度阈值（默认 10），超过此值的函数会被标记",
            },
        },
        "required": ["path"],
    },
)
def complexity_report(path: str, threshold: int = 10) -> dict:
    """计算代码复杂度报告"""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    if p.is_file():
        py_files = [p] if p.suffix == ".py" else []
    else:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        py_files = sorted(
            f for f in p.rglob("*.py")
            if not any(part in skip for part in f.relative_to(p).parts)
        )[:100]

    if not py_files:
        return {"error": "未找到 Python 文件"}

    base = p if p.is_dir() else p.parent
    all_functions = []
    file_stats = []

    for fp in py_files:
        tree = _safe_parse(fp)
        if not tree:
            continue

        rel = str(fp.relative_to(base)) if fp != base else fp.name
        lines = len(fp.read_text(encoding="utf-8", errors="ignore").splitlines())
        funcs_in_file = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = _cyclomatic_complexity(node)
                cog = _cognitive_complexity(node)
                func_lines = (node.end_lineno or node.lineno) - node.lineno + 1
                info = {
                    "name": node.name,
                    "file": rel,
                    "line": node.lineno,
                    "lines": func_lines,
                    "cyclomatic": cc,
                    "cognitive": cog,
                }
                if cc >= threshold or cog >= threshold:
                    info["risk"] = "HIGH"
                elif cc >= threshold * 0.6 or cog >= threshold * 0.6:
                    info["risk"] = "MEDIUM"
                all_functions.append(info)
                funcs_in_file.append(info)

        if funcs_in_file:
            avg_cc = sum(f["cyclomatic"] for f in funcs_in_file) / len(funcs_in_file)
            file_stats.append({
                "file": rel,
                "total_lines": lines,
                "functions": len(funcs_in_file),
                "avg_complexity": round(avg_cc, 1),
            })

    # 按复杂度排序取 top
    high_risk = sorted(
        [f for f in all_functions if f.get("risk") == "HIGH"],
        key=lambda x: -x["cyclomatic"]
    )
    medium_risk = sorted(
        [f for f in all_functions if f.get("risk") == "MEDIUM"],
        key=lambda x: -x["cyclomatic"]
    )

    total_cc = sum(f["cyclomatic"] for f in all_functions) if all_functions else 0
    avg_cc = total_cc / max(len(all_functions), 1)

    return {
        "summary": {
            "total_files": len(py_files),
            "total_functions": len(all_functions),
            "avg_complexity": round(avg_cc, 1),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "threshold": threshold,
        },
        "high_risk_functions": high_risk[:20],
        "medium_risk_functions": medium_risk[:20],
        "file_stats": sorted(file_stats, key=lambda x: -x["avg_complexity"])[:30],
    }


# ===== 内部辅助函数 =====

def _name_of(node) -> str:
    """从 AST 节点提取名称字符串"""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        value = _name_of(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Subscript):
        return _name_of(node.value)
    return ""


def _call_name(node: ast.Call) -> str:
    """从 Call 节点提取被调用函数的名称"""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _cyclomatic_complexity(node: ast.FunctionDef) -> int:
    """计算函数的圈复杂度（McCabe CC）

    CC = 1 + 分支数（if/elif/for/while/except/with/assert/and/or/三目）
    """
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            cc += 1
        elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
            cc += 1
        elif isinstance(child, ast.ExceptHandler):
            cc += 1
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            cc += 1
        elif isinstance(child, ast.Assert):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            # and/or 每个操作符 +1
            cc += len(child.values) - 1
    return cc


def _cognitive_complexity(node: ast.FunctionDef) -> int:
    """计算函数的认知复杂度

    认知复杂度比圈复杂度更能反映代码的可读性：
    - 嵌套增加权重
    - break/continue 增加 +1
    - 递归调用增加 +1
    """
    score = 0
    func_name = node.name

    def _walk(n, nesting=0):
        nonlocal score
        for child in ast.iter_child_nodes(n):
            increment = 0
            nest_increase = 0

            if isinstance(child, (ast.If, ast.IfExp)):
                increment = 1 + nesting
                nest_increase = 1
            elif isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                increment = 1 + nesting
                nest_increase = 1
            elif isinstance(child, ast.ExceptHandler):
                increment = 1 + nesting
                nest_increase = 1
            elif isinstance(child, ast.BoolOp):
                increment = len(child.values) - 1
            elif isinstance(child, (ast.Break, ast.Continue)):
                increment = 1
            elif isinstance(child, ast.Call):
                callee = _call_name(child)
                if callee == func_name:
                    increment = 1  # 递归

            score += increment
            _walk(child, nesting + nest_increase)

    _walk(node)
    return score
