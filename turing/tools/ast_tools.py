"""AST 智能代码分析工具

提供多语言代码深度理解能力（对标 Gemini/Codex 的代码分析能力）：
- code_structure    — 提取文件的类、函数、导入等结构信息
- call_graph        — 分析函数调用关系图
- complexity_report — 计算代码复杂度并识别热点

支持语言：
- Python（内置 ast 模块，完整支持）
- JavaScript / TypeScript / Go / Rust / Java（通过 tree-sitter，结构提取）
"""

from __future__ import annotations

import ast
import os
import re
from collections import defaultdict
from pathlib import Path

from turing.tools.registry import tool

# ===== tree-sitter 多语言支持 =====
try:
    import tree_sitter_languages
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

# 语言后缀映射
_LANG_MAP: dict[str, str] = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rb": "ruby",
    ".py": "python",
}

# 支持 tree-sitter 分析的后缀集合（不含 .py，Python 用内置 ast）
_TS_SUPPORTED = {k for k, v in _LANG_MAP.items() if v != "python"}


def _safe_parse(filepath: Path) -> ast.Module | None:
    """安全地解析 Python 文件，失败返回 None"""
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        return ast.parse(source, filename=str(filepath))
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return None


def _ts_parse(filepath: Path) -> tuple | None:
    """用 tree-sitter 解析非 Python 文件，返回 (tree, language_name) 或 None"""
    if not HAS_TREE_SITTER:
        return None
    lang = _LANG_MAP.get(filepath.suffix.lower())
    if not lang or lang == "python":
        return None
    try:
        parser = tree_sitter_languages.get_parser(lang)
        source = filepath.read_bytes()
        tree = parser.parse(source)
        return (tree, lang)
    except Exception:
        return None


def _ts_extract_structure(filepath: Path, include_private: bool) -> dict | None:
    """用 tree-sitter 提取非 Python 文件的代码结构"""
    result = _ts_parse(filepath)
    if result is None:
        return None

    tree, lang = result
    source = filepath.read_bytes()
    root = tree.root_node

    classes = []
    functions = []
    imports = []
    global_vars = []

    def _node_text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _extract_name(node):
        """从节点中提取名称"""
        for child in node.children:
            if child.type in ("identifier", "type_identifier", "property_identifier"):
                return _node_text(child)
        return ""

    for child in root.children:
        ntype = child.type

        # --- 函数/方法 ---
        if ntype in ("function_declaration", "function_definition", "method_definition",
                      "function_item", "method_declaration",
                      "arrow_function", "lexical_declaration"):
            name = ""
            is_async = False

            if ntype == "lexical_declaration":
                # const foo = (...) => {...} 或 const foo = function(...) {...}
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name = _extract_name(decl)
                        # 检查值是否是箭头函数或函数表达式
                        for val in decl.children:
                            if val.type in ("arrow_function", "function"):
                                break
                        else:
                            name = ""  # 不是函数赋值，跳过
                if not name:
                    # 普通变量声明 → global_vars
                    for decl in child.children:
                        if decl.type == "variable_declarator":
                            vname = _extract_name(decl)
                            if vname and (include_private or not vname.startswith("_")):
                                global_vars.append({"name": vname, "line": child.start_point[0] + 1})
                    continue
            else:
                name = _extract_name(child)

            if not name:
                continue
            if not include_private and name.startswith("_"):
                continue

            # 检查 async
            first_text = _node_text(child.children[0]) if child.children else ""
            if first_text == "async":
                is_async = True

            # 提取参数
            args = []
            for sub in child.children:
                if sub.type in ("formal_parameters", "parameter_list", "parameters"):
                    for param in sub.children:
                        pname = _extract_name(param) if param.type != "," else ""
                        if not pname and param.type in ("identifier", "simple_identifier"):
                            pname = _node_text(param)
                        if pname and pname not in ("(", ")", ",", "self", "this"):
                            args.append(pname)

            functions.append({
                "name": name,
                "line": child.start_point[0] + 1,
                "args": args,
                "is_async": is_async,
            })

        # --- 类/结构体 ---
        elif ntype in ("class_declaration", "class_definition", "struct_item",
                        "impl_item", "interface_declaration", "type_declaration"):
            name = _extract_name(child)
            if not name:
                continue
            if not include_private and name.startswith("_"):
                continue

            methods = []
            # 在类体中查找方法
            for sub in child.children:
                if sub.type in ("class_body", "declaration_list", "block"):
                    for member in sub.children:
                        if member.type in ("method_definition", "function_definition",
                                           "function_item", "method_declaration",
                                           "public_field_definition"):
                            mname = _extract_name(member)
                            if mname and (include_private or not mname.startswith("_")):
                                m_args = []
                                for mp in member.children:
                                    if mp.type in ("formal_parameters", "parameter_list", "parameters"):
                                        for param in mp.children:
                                            pn = _extract_name(param)
                                            if pn and pn not in ("(", ")", ",", "self", "this"):
                                                m_args.append(pn)
                                methods.append({
                                    "name": mname,
                                    "line": member.start_point[0] + 1,
                                    "args": m_args,
                                    "is_async": any(_node_text(c) == "async" for c in member.children[:2]),
                                })

            classes.append({
                "name": name,
                "line": child.start_point[0] + 1,
                "bases": [],
                "methods": methods,
            })

        # --- 导入 ---
        elif ntype in ("import_statement", "import_declaration", "use_declaration",
                        "package_clause"):
            imports.append(_node_text(child).strip().rstrip(";"))

        # --- 全局变量 ---
        elif ntype in ("variable_declaration", "const_declaration", "let_declaration",
                        "static_item", "const_item"):
            vname = _extract_name(child)
            if vname and (include_private or not vname.startswith("_")):
                global_vars.append({"name": vname, "line": child.start_point[0] + 1})

    total_lines = len(source.decode("utf-8", errors="replace").splitlines())

    return {
        "file": str(filepath),
        "language": lang,
        "total_lines": total_lines,
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "global_vars": global_vars,
    }


@tool(
    name="code_structure",
    description="解析源代码文件的 AST，提取类、函数、全局变量、导入等结构信息。"
                "支持 Python/JavaScript/TypeScript/Go/Rust/Java/C/C++/Ruby。"
                "可用于快速理解文件组织结构，无需逐行阅读。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "源代码文件或目录路径",
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
    """提取源代码文件 / 目录的代码结构（多语言支持）"""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    supported_exts = {".py"} | _TS_SUPPORTED

    if p.is_file():
        if p.suffix == ".py":
            return _extract_structure(p, include_private)
        elif p.suffix.lower() in _TS_SUPPORTED:
            result = _ts_extract_structure(p, include_private)
            if result is None:
                return {"error": f"tree-sitter 未安装，无法分析 {p.suffix} 文件。请 pip install tree-sitter-languages"}
            return result
        else:
            return {"error": f"不支持的文件类型: {p.suffix}。支持: {', '.join(sorted(supported_exts))}"}

    # 目录模式：汇总所有支持的文件
    results = {}
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    code_files = sorted(
        f for f in p.rglob("*")
        if f.is_file()
        and f.suffix.lower() in supported_exts
        and not any(part in skip for part in f.relative_to(p).parts)
    )
    if len(code_files) > 100:
        code_files = code_files[:100]

    for fp in code_files:
        rel = str(fp.relative_to(p))
        if fp.suffix == ".py":
            info = _extract_structure(fp, include_private)
        else:
            info = _ts_extract_structure(fp, include_private) or {"error": "tree-sitter 未安装"}
        if info.get("classes") or info.get("functions") or info.get("global_vars"):
            results[rel] = info

    return {
        "directory": str(p),
        "total_files": len(code_files),
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
    description="分析源代码文件 / 目录的函数调用关系图。"
                "支持 Python（完整）和其他语言（tree-sitter 基础分析）。"
                "识别哪些函数调用了哪些函数，帮助理解代码执行流程和依赖关系。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "源代码文件或目录路径",
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

    supported_exts = {".py"} | _TS_SUPPORTED

    # 收集所有源代码文件
    if p.is_file():
        code_files = [p] if p.suffix.lower() in supported_exts else []
    else:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        code_files = sorted(
            f for f in p.rglob("*")
            if f.is_file()
            and f.suffix.lower() in supported_exts
            and not any(part in skip for part in f.relative_to(p).parts)
        )[:80]

    if not code_files:
        return {"error": "未找到支持的源代码文件"}

    # 分离 Python 和非 Python 文件
    py_files = [f for f in code_files if f.suffix == ".py"]
    ts_files = [f for f in code_files if f.suffix.lower() in _TS_SUPPORTED]

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

    # tree-sitter 文件：提取定义
    for fp in ts_files:
        info = _ts_extract_structure(fp, include_private=True)
        if not info:
            continue
        rel = str(fp.relative_to(base)) if fp != base else fp.name
        for func in info.get("functions", []):
            all_defs[func["name"]] = {"file": rel, "line": func["line"], "type": "function"}
        for cls in info.get("classes", []):
            all_defs[cls["name"]] = {"file": rel, "line": cls["line"], "type": "class"}

    # 第二遍：收集调用关系（Python 文件用 AST 精确分析）
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
                        # v6.0: qualified name — 先完整匹配，再回退到裸名
                        if callee and callee != caller:
                            if callee in all_defs:
                                calls[caller].add(callee)
                                callers[callee].add(caller)
                            else:
                                bare = callee.rsplit(".", 1)[-1]
                                if bare in all_defs and bare != caller:
                                    calls[caller].add(bare)
                                    callers[bare].add(caller)

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
    description="计算代码的圈复杂度和认知复杂度，识别需要重构的高复杂度函数。"
                "支持 Python（精确计算）和其他语言（tree-sitter 行数估算）。"
                "高复杂度函数是 bug 密集区，应优先重构。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "源代码文件或目录路径",
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
    """计算代码复杂度报告（多语言支持）"""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"路径不存在: {path}"}

    supported_exts = {".py"} | _TS_SUPPORTED

    if p.is_file():
        code_files = [p] if p.suffix.lower() in supported_exts else []
    else:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        code_files = sorted(
            f for f in p.rglob("*")
            if f.is_file()
            and f.suffix.lower() in supported_exts
            and not any(part in skip for part in f.relative_to(p).parts)
        )[:100]

    if not code_files:
        return {"error": "未找到支持的源代码文件"}

    base = p if p.is_dir() else p.parent
    all_functions = []
    file_stats = []

    for fp in code_files:
        rel = str(fp.relative_to(base)) if fp != base else fp.name
        lines = len(fp.read_text(encoding="utf-8", errors="ignore").splitlines())
        funcs_in_file = []

        if fp.suffix == ".py":
            # Python：精确 AST 分析
            tree = _safe_parse(fp)
            if not tree:
                continue
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
        else:
            # 非 Python：用 tree-sitter 提取函数，行数估算复杂度
            ts_info = _ts_extract_structure(fp, include_private=True)
            if not ts_info:
                continue
            for func in ts_info.get("functions", []):
                func_lines = max(func.get("lines", 10), 1)
                # 简单估算：行数 / 5 作为圈复杂度近似值
                cc = max(1, func_lines // 5)
                info = {
                    "name": func["name"],
                    "file": rel,
                    "line": func["line"],
                    "lines": func_lines,
                    "cyclomatic": cc,
                    "cognitive": cc,  # 无法精确计算，用 cc 近似
                }
                if cc >= threshold:
                    info["risk"] = "HIGH"
                elif cc >= threshold * 0.6:
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
    """从 Call 节点提取被调用函数的名称（v6.0: 返回限定名避免假边）"""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        # 返回 "obj.method" 而非仅 "method"，避免同名方法产生假边
        value = _name_of(node.func.value)
        return f"{value}.{node.func.attr}" if value else node.func.attr
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


# ────────────────── 依赖关系图工具 ──────────────────


@tool(
    name="dependency_graph",
    description="生成项目的模块级依赖关系图。分析 import 关系，识别循环依赖、"
                "核心模块（被依赖最多）、叶子模块（无依赖），"
                "以及分层结构。支持 Python 项目。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目根目录路径（默认当前目录）",
            },
            "max_depth": {
                "type": "integer",
                "description": "最大分析深度（默认 5）",
            },
        },
        "required": [],
    },
)
def dependency_graph(path: str = ".", max_depth: int = 5) -> dict:
    """生成模块级依赖关系图。"""
    p = Path(path).resolve()
    if not p.exists() or not p.is_dir():
        return {"error": f"目录不存在: {path}"}

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".tox", ".eggs"}

    # 收集所有 Python 文件
    py_files = []
    for f in sorted(p.rglob("*.py")):
        if any(part in skip for part in f.relative_to(p).parts):
            continue
        py_files.append(f)
        if len(py_files) >= 200:
            break

    if not py_files:
        return {"error": "未找到 Python 文件"}

    # 构建模块名映射
    module_map = {}  # module_dotted_name -> filepath
    for fp in py_files:
        rel = fp.relative_to(p)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")
        mod_name = ".".join(parts)
        if mod_name:
            module_map[mod_name] = str(rel)

    # 分析每个模块的 import
    edges = {}  # module -> set of imported modules
    for fp in py_files:
        tree = _safe_parse(fp)
        if not tree:
            continue
        rel = fp.relative_to(p)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].replace(".py", "")
        mod_name = ".".join(parts)
        if not mod_name:
            continue

        deps = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # 检查是否为项目内模块
                    imp = alias.name
                    for known in module_map:
                        if imp == known or imp.startswith(known + "."):
                            deps.add(known)
                            break
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imp = node.module
                    for known in module_map:
                        if imp == known or imp.startswith(known + "."):
                            deps.add(known)
                            break

        deps.discard(mod_name)  # 不计自引用
        if deps:
            edges[mod_name] = sorted(deps)

    # 统计被依赖次数
    dep_count = {}  # module -> number of times depended on
    for mod, deps in edges.items():
        for d in deps:
            dep_count[d] = dep_count.get(d, 0) + 1

    # 识别核心模块（被依赖最多）
    core_modules = sorted(dep_count.items(), key=lambda x: -x[1])[:10]

    # 识别叶子模块（不被其他模块依赖）
    all_modules = set(module_map.keys())
    depended_on = set(dep_count.keys())
    leaf_modules = sorted(all_modules - depended_on)[:20]

    # 循环依赖检测
    cycles = []
    visited = set()
    path_stack = []

    def _find_cycles(node, stack_set):
        if node in stack_set:
            # 找到循环
            cycle_start = path_stack.index(node)
            cycle = path_stack[cycle_start:] + [node]
            normalized = tuple(sorted(cycle))
            if normalized not in visited:
                visited.add(normalized)
                cycles.append(cycle)
            return
        if node in visited and node not in stack_set:
            return
        stack_set.add(node)
        path_stack.append(node)
        for dep in edges.get(node, []):
            _find_cycles(dep, stack_set)
        path_stack.pop()
        stack_set.discard(node)

    for mod in sorted(edges.keys()):
        _find_cycles(mod, set())

    # 分层排序（拓扑序）
    layers = []
    remaining = set(edges.keys()) | set(m for deps in edges.values() for m in deps)
    assigned = set()
    for _ in range(max_depth):
        # 当前层：没有未分配依赖的模块
        layer = []
        for mod in sorted(remaining - assigned):
            deps = set(edges.get(mod, []))
            if deps <= assigned or not deps:
                layer.append(mod)
        if not layer:
            break
        layers.append(layer)
        assigned.update(layer)

    # 未分配的（可能有循环依赖）
    unassigned = sorted((remaining - assigned) & set(edges.keys()))
    if unassigned:
        layers.append(unassigned)

    return {
        "total_modules": len(module_map),
        "total_edges": sum(len(v) for v in edges.values()),
        "core_modules": [{"module": m, "depended_by": c} for m, c in core_modules],
        "leaf_modules": leaf_modules,
        "cycles": cycles[:10],
        "has_cycles": len(cycles) > 0,
        "layers": layers,
        "graph": {k: v for k, v in sorted(edges.items())[:50]},
    }
