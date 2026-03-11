"""搜索工具

- search_code — 在代码库中搜索文本 / 正则（优先使用 ripgrep，回退 grep）
- list_directory — 列出目录内容
- repo_map — 生成代码库符号级地图
- smart_context — 智能上下文收集（基于引用链 + 依赖追踪）
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
    """文本/正则搜索代码（优先使用 ripgrep，降级为 grep）。"""
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
    """列出目录内容（支持递归和文件大小显示）。"""
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


@tool(
    name="repo_map",
    description="生成代码库的符号级地图（对标 Aider 的 Repo Map）。"
                "快速展示每个文件的关键符号（类、函数、常量），"
                "帮助理解代码库全貌和文件职责，无需逐一阅读。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目根目录路径（默认当前目录）",
            },
            "max_files": {
                "type": "integer",
                "description": "最大扫描文件数（默认 100）",
            },
        },
        "required": [],
    },
)
def repo_map(path: str = ".", max_files: int = 100) -> dict:
    """生成代码仓库结构地图（模块 + 函数 + 类）。"""
    """生成代码库符号级地图"""
    import ast as _ast

    p = Path(path).resolve()
    if not p.exists() or not p.is_dir():
        return {"error": f"目录不存在: {path}"}

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv",
            "dist", "build", ".tox", ".eggs", ".mypy_cache"}
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}

    # 收集代码文件
    code_files = []
    for f in sorted(p.rglob("*")):
        if any(part in skip for part in f.relative_to(p).parts):
            continue
        if f.is_file() and f.suffix in code_exts:
            code_files.append(f)
        if len(code_files) >= max_files:
            break

    file_map = {}
    total_symbols = 0

    for fp in code_files:
        rel = str(fp.relative_to(p))
        symbols = {"classes": [], "functions": [], "exports": []}

        if fp.suffix == ".py":
            # Python: full AST parsing
            try:
                source = fp.read_text(encoding="utf-8", errors="ignore")
                tree = _ast.parse(source, filename=rel)
                for node in _ast.iter_child_nodes(tree):
                    if isinstance(node, _ast.ClassDef):
                        methods = [
                            n.name for n in _ast.iter_child_nodes(node)
                            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                            and not n.name.startswith("_")
                        ]
                        symbols["classes"].append({
                            "name": node.name,
                            "line": node.lineno,
                            "methods": methods[:10],
                        })
                    elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        if not node.name.startswith("_"):
                            symbols["functions"].append({
                                "name": node.name,
                                "line": node.lineno,
                            })
            except (SyntaxError, ValueError):
                symbols["error"] = "parse_failed"
        else:
            # JS/TS/Go/Rust/Java: regex-based symbol extraction
            try:
                source = fp.read_text(encoding="utf-8", errors="ignore")
                import re
                # Class/struct/interface
                for m in re.finditer(
                    r'^(?:export\s+)?(?:class|struct|interface|type)\s+(\w+)',
                    source, re.MULTILINE
                ):
                    symbols["classes"].append({"name": m.group(1)})
                # Functions
                for m in re.finditer(
                    r'^(?:export\s+)?(?:function|func|fn|def|pub fn|async function)\s+(\w+)',
                    source, re.MULTILINE
                ):
                    symbols["functions"].append({"name": m.group(1)})
                # Export declarations (JS/TS)
                for m in re.finditer(
                    r'^export\s+(?:default\s+)?(?:const|let|var)\s+(\w+)',
                    source, re.MULTILINE
                ):
                    symbols["exports"].append(m.group(1))
            except Exception:
                symbols["error"] = "parse_failed"

        # 只保留有内容的文件
        sym_count = len(symbols.get("classes", [])) + len(symbols.get("functions", [])) + len(symbols.get("exports", []))
        if sym_count > 0 or "error" in symbols:
            # 清理空列表
            clean = {}
            for k, v in symbols.items():
                if v:
                    clean[k] = v
            file_map[rel] = clean
            total_symbols += sym_count

    # 生成紧凑的文本地图（供 LLM 阅读）
    text_map_lines = []
    for rel_path, syms in sorted(file_map.items()):
        parts = []
        for cls in syms.get("classes", []):
            meths = ", ".join(cls.get("methods", []))
            if meths:
                parts.append(f"class {cls['name']}({meths})")
            else:
                parts.append(f"class {cls['name']}")
        for fn in syms.get("functions", []):
            parts.append(f"def {fn['name']}")
        for exp in syms.get("exports", []):
            parts.append(f"export {exp}")
        if parts:
            text_map_lines.append(f"  {rel_path}: {'; '.join(parts)}")

    text_map = "\n".join(text_map_lines)

    return {
        "total_files": len(code_files),
        "mapped_files": len(file_map),
        "total_symbols": total_symbols,
        "map": file_map,
        "text_map": text_map,
    }


@tool(
    name="smart_context",
    description="智能上下文收集：基于错误堆栈、import 链或符号引用，自动定位并返回最相关的代码片段。对标 Claude Code / Cursor 的上下文感知能力。",
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "目标文件路径或符号名",
            },
            "mode": {
                "type": "string",
                "description": "模式: imports（追踪导入链）/ references（符号引用）/ error_trace（解析错误堆栈）",
                "enum": ["imports", "references", "error_trace"],
            },
            "error_text": {
                "type": "string",
                "description": "错误堆栈文本（mode=error_trace 时使用）",
            },
            "max_files": {
                "type": "integer",
                "description": "最大返回文件数，默认 10",
            },
        },
        "required": ["target", "mode"],
    },
)
def smart_context(target: str, mode: str = "imports", error_text: str = "",
                  max_files: int = 10) -> dict:
    """智能上下文收集，基于代码关系自动定位关键文件。"""
    import ast as _ast
    import re

    if mode == "error_trace":
        return _parse_error_trace(error_text or target, max_files)
    elif mode == "imports":
        return _trace_imports(target, max_files)
    elif mode == "references":
        return _find_references(target, max_files)
    return {"error": f"未知模式: {mode}"}


def _parse_error_trace(error_text: str, max_files: int) -> dict:
    """从堆栈追踪中提取文件和行号"""
    import re
    # 匹配 Python traceback: File "path", line N
    pattern = re.compile(r'File "([^"]+)", line (\d+)')
    files = []
    seen = set()
    for m in pattern.finditer(error_text):
        filepath, lineno = m.group(1), int(m.group(2))
        if filepath not in seen and Path(filepath).exists():
            seen.add(filepath)
            # 读取错误行附近的上下文
            try:
                lines = Path(filepath).read_text(encoding="utf-8", errors="ignore").split("\n")
                start = max(0, lineno - 5)
                end = min(len(lines), lineno + 5)
                context = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
                files.append({
                    "path": filepath,
                    "line": lineno,
                    "context": context,
                })
            except Exception:
                files.append({"path": filepath, "line": lineno})
        if len(files) >= max_files:
            break
    return {"mode": "error_trace", "files": files, "count": len(files)}


def _trace_imports(target: str, max_files: int) -> dict:
    """追踪 Python 文件的 import 依赖链"""
    import ast as _ast

    target_path = Path(target).resolve()
    if not target_path.exists():
        return {"error": f"文件不存在: {target}"}

    visited = set()
    imports = []

    def _extract_imports(filepath: Path, depth: int = 0):
        if filepath in visited or depth > 3 or len(imports) >= max_files:
            return
        visited.add(filepath)
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
            tree = _ast.parse(source)
        except Exception:
            return

        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    resolved = _resolve_module(alias.name, filepath)
                    if resolved and resolved not in visited:
                        imports.append({
                            "module": alias.name,
                            "path": str(resolved),
                            "depth": depth + 1,
                        })
                        _extract_imports(resolved, depth + 1)
            elif isinstance(node, _ast.ImportFrom):
                if node.module:
                    resolved = _resolve_module(node.module, filepath)
                    if resolved and resolved not in visited:
                        names = [a.name for a in node.names] if node.names else []
                        imports.append({
                            "module": node.module,
                            "path": str(resolved),
                            "depth": depth + 1,
                            "names": names[:10],
                        })
                        _extract_imports(resolved, depth + 1)

    _extract_imports(target_path)
    return {"mode": "imports", "target": target, "imports": imports[:max_files], "count": len(imports)}


def _resolve_module(module_name: str, source_file: Path) -> Path | None:
    """尝试将模块名解析为文件路径"""
    parts = module_name.split(".")
    # 从源文件所在目录开始搜索
    search_dirs = [source_file.parent, Path.cwd()]
    for base in search_dirs:
        candidate = base / "/".join(parts)
        if candidate.with_suffix(".py").exists():
            return candidate.with_suffix(".py")
        if (candidate / "__init__.py").exists():
            return candidate / "__init__.py"
    return None


def _find_references(symbol: str, max_files: int) -> dict:
    """在代码库中查找符号的所有引用"""
    import re

    # 使用 word boundary 精确匹配
    pattern = re.compile(rf'\b{re.escape(symbol)}\b')
    results = []
    cwd = Path.cwd()
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"}

    for fp in sorted(cwd.rglob("*")):
        if any(part in skip for part in fp.relative_to(cwd).parts):
            continue
        if not fp.is_file() or fp.suffix not in code_exts:
            continue
        try:
            source = fp.read_text(encoding="utf-8", errors="ignore")
            matches = []
            for i, line in enumerate(source.split("\n"), 1):
                if pattern.search(line):
                    matches.append({"line": i, "text": line.strip()[:120]})
            if matches:
                results.append({
                    "path": str(fp.relative_to(cwd)),
                    "matches": matches[:10],
                    "total_matches": len(matches),
                })
        except Exception:
            continue
        if len(results) >= max_files:
            break

    return {
        "mode": "references",
        "symbol": symbol,
        "files": results,
        "count": len(results),
    }
