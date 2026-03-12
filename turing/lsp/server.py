"""Turing LSP 补全服务器

实现 Language Server Protocol 的核心子集：
- textDocument/completion — 代码补全
- textDocument/didOpen / didChange — 文档同步
- initialized / shutdown / exit — 生命周期

架构：
- 基于 JSON-RPC 2.0 over stdio
- 利用 Turing 的 AST 分析工具提取符号信息
- 支持本地 LLM 生成智能补全（可选）

启动方式::

    python -m turing.lsp         # stdio 模式
    python -m turing.lsp --port 2087  # TCP 模式（未来扩展）

VS Code 集成::

    在 .vscode/settings.json 中配置:
    {
        "turing.lsp.enabled": true,
        "turing.lsp.pythonPath": "python3"
    }
"""

from __future__ import annotations

import ast
import json
import sys
import re
from pathlib import Path
from typing import Any


class TuringLSPServer:
    """Turing LSP 服务器核心

    实现 LSP 的核心子集：
    - textDocument/completion — 代码补全
    - textDocument/hover — 悬停信息
    - textDocument/definition — 跳转到定义
    - textDocument/publishDiagnostics — 诊断（lint/语法错误）
    - textDocument/codeAction — 代码操作（快速修复）
    """

    def __init__(self):
        self._documents: dict[str, str] = {}  # uri -> content
        self._symbol_cache: dict[str, list[dict]] = {}  # uri -> symbols
        self._diagnostics_cache: dict[str, list[dict]] = {}  # uri -> diagnostics
        self._running = True

    def run_stdio(self):
        """以 stdio 模式运行 LSP 服务器"""
        while self._running:
            try:
                message = self._read_message()
                if message is None:
                    break
                response = self._handle_message(message)
                if response is not None:
                    self._write_message(response)
            except (EOFError, BrokenPipeError):
                break
            except Exception:
                continue

    def _read_message(self) -> dict | None:
        """从 stdin 读取 LSP 消息"""
        _MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB
        _MAX_HEADERS = 32
        headers = {}
        header_count = 0
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            line = line.decode("utf-8").strip()
            if not line:
                break
            header_count += 1
            if header_count > _MAX_HEADERS:
                return None
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        content_length = int(headers.get("Content-Length", 0))
        if content_length <= 0:
            return None
        # v10.0: 拒绝超大消息防 OOM
        if content_length > _MAX_MESSAGE_SIZE:
            sys.stdin.buffer.read(content_length)
            return None

        body = sys.stdin.buffer.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _write_message(self, msg: dict):
        """向 stdout 写入 LSP 消息"""
        body = json.dumps(msg, ensure_ascii=False)
        body_bytes = body.encode("utf-8")
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
        sys.stdout.buffer.write(header.encode("utf-8") + body_bytes)
        sys.stdout.buffer.flush()

    def _handle_message(self, msg: dict) -> dict | None:
        """分发 LSP 消息到对应处理器"""
        method = msg.get("method", "")
        params = msg.get("params", {})
        msg_id = msg.get("id")

        # 请求（需要响应）
        if msg_id is not None:
            result = self._dispatch_request(method, params)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result,
            }

        # 通知（不需要响应）
        self._dispatch_notification(method, params)
        return None

    def _dispatch_request(self, method: str, params: dict) -> Any:
        """处理请求类消息"""
        if method == "initialize":
            return self._handle_initialize(params)
        elif method == "textDocument/completion":
            return self._handle_completion(params)
        elif method == "textDocument/hover":
            return self._handle_hover(params)
        elif method == "textDocument/definition":
            return self._handle_definition(params)
        elif method == "textDocument/codeAction":
            return self._handle_code_action(params)
        elif method == "shutdown":
            self._running = False
            return None
        return None

    def _dispatch_notification(self, method: str, params: dict):
        """处理通知类消息"""
        if method == "textDocument/didOpen":
            self._handle_did_open(params)
        elif method == "textDocument/didChange":
            self._handle_did_change(params)
        elif method == "exit":
            self._running = False

    def _handle_initialize(self, params: dict) -> dict:
        """处理 initialize 请求"""
        return {
            "capabilities": {
                "completionProvider": {
                    "triggerCharacters": [".", "(", " ", ":", "@"],
                    "resolveProvider": False,
                },
                "textDocumentSync": {
                    "openClose": True,
                    "change": 1,  # Full sync
                },
                "hoverProvider": True,
                "definitionProvider": True,
                "codeActionProvider": True,
            },
            "serverInfo": {
                "name": "turing-lsp",
                "version": "0.2.0",
            },
        }

    def _handle_did_open(self, params: dict):
        """文档打开通知"""
        doc = params.get("textDocument", {})
        uri = doc.get("uri", "")
        text = doc.get("text", "")
        self._documents[uri] = text
        self._update_symbols(uri, text)
        self._publish_diagnostics(uri, text)

    def _handle_did_change(self, params: dict):
        """文档变更通知"""
        doc = params.get("textDocument", {})
        uri = doc.get("uri", "")
        changes = params.get("contentChanges", [])
        if changes:
            text = changes[-1].get("text", "")
            self._documents[uri] = text
            self._update_symbols(uri, text)
            self._publish_diagnostics(uri, text)

    def _handle_completion(self, params: dict) -> dict:
        """处理代码补全请求"""
        doc = params.get("textDocument", {})
        uri = doc.get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)

        text = self._documents.get(uri, "")
        if not text:
            return {"isIncomplete": False, "items": []}

        lines = text.split("\n")
        if line >= len(lines):
            return {"isIncomplete": False, "items": []}

        current_line = lines[line]
        prefix = current_line[:character]

        items = []

        # 1. 基于当前文件的符号补全
        symbols = self._symbol_cache.get(uri, [])
        for sym in symbols:
            name = sym.get("name", "")
            if not name:
                continue
            items.append({
                "label": name,
                "kind": self._symbol_kind(sym.get("type", "")),
                "detail": sym.get("detail", ""),
                "documentation": sym.get("doc", ""),
            })

        # 2. 点号触发的属性补全
        dot_match = re.search(r'(\w+)\.$', prefix)
        if dot_match:
            obj_name = dot_match.group(1)
            items.extend(self._get_attribute_completions(uri, text, obj_name))

        # 3. import 补全
        import_match = re.match(r'\s*(?:from\s+(\S+)\s+import\s*|import\s+)', prefix)
        if import_match:
            items.extend(self._get_import_completions(uri, prefix))

        # 4. Python 关键字和内置函数补全
        word_match = re.search(r'(\w+)$', prefix)
        if word_match:
            partial = word_match.group(1)
            items.extend(self._get_keyword_completions(partial))

        # 去重
        seen = set()
        unique = []
        for item in items:
            if item["label"] not in seen:
                seen.add(item["label"])
                unique.append(item)

        return {
            "isIncomplete": len(unique) >= 50,
            "items": unique[:50],
        }

    def _update_symbols(self, uri: str, text: str):
        """更新文件的符号缓存"""
        symbols = []
        try:
            tree = ast.parse(text)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append({
                        "name": node.name,
                        "type": "class",
                        "detail": f"class {node.name}",
                        "line": node.lineno,
                    })
                    # 提取方法
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            args = [a.arg for a in item.args.args if a.arg != "self"]
                            symbols.append({
                                "name": item.name,
                                "type": "method",
                                "detail": f"def {item.name}({', '.join(args)})",
                                "line": item.lineno,
                                "parent": node.name,
                            })
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args]
                    symbols.append({
                        "name": node.name,
                        "type": "function",
                        "detail": f"def {node.name}({', '.join(args)})",
                        "line": node.lineno,
                    })
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            symbols.append({
                                "name": target.id,
                                "type": "variable",
                                "line": node.lineno,
                            })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        for alias in node.names:
                            name = alias.asname or alias.name
                            symbols.append({
                                "name": name,
                                "type": "import",
                                "detail": f"from {node.module} import {alias.name}",
                            })
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name
                            symbols.append({
                                "name": name,
                                "type": "import",
                                "detail": f"import {alias.name}",
                            })
        except (SyntaxError, ValueError):
            pass

        self._symbol_cache[uri] = symbols

    def _get_attribute_completions(self, uri: str, text: str,
                                   obj_name: str) -> list[dict]:
        """获取对象属性补全"""
        items = []
        symbols = self._symbol_cache.get(uri, [])

        # 查找是否是类实例
        for sym in symbols:
            if sym.get("name") == obj_name and sym.get("type") == "class":
                # 返回该类的方法
                for s in symbols:
                    if s.get("parent") == obj_name:
                        items.append({
                            "label": s["name"],
                            "kind": 2,  # Method
                            "detail": s.get("detail", ""),
                        })
                break

        return items

    def _get_import_completions(self, uri: str, prefix: str) -> list[dict]:
        """获取 import 补全"""
        items = []
        # 标准库常用模块
        common_modules = [
            "os", "sys", "json", "re", "pathlib", "typing", "collections",
            "functools", "itertools", "datetime", "math", "subprocess",
            "logging", "unittest", "dataclasses", "abc", "textwrap",
            "hashlib", "uuid", "time", "shutil", "io", "copy",
        ]
        for mod in common_modules:
            items.append({
                "label": mod,
                "kind": 9,  # Module
                "detail": f"Python stdlib: {mod}",
            })
        return items

    def _get_keyword_completions(self, partial: str) -> list[dict]:
        """获取关键字补全"""
        keywords = [
            "def", "class", "import", "from", "return", "yield",
            "if", "elif", "else", "for", "while", "break", "continue",
            "try", "except", "finally", "raise", "with", "as",
            "pass", "lambda", "async", "await", "True", "False", "None",
            "and", "or", "not", "in", "is", "global", "nonlocal",
            "assert", "del",
        ]
        builtins = [
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "reversed", "list", "dict", "set", "tuple", "str",
            "int", "float", "bool", "type", "isinstance", "issubclass",
            "getattr", "setattr", "hasattr", "open", "super", "property",
            "staticmethod", "classmethod", "abstractmethod",
        ]

        items = []
        for kw in keywords:
            if kw.startswith(partial) and kw != partial:
                items.append({
                    "label": kw,
                    "kind": 14,  # Keyword
                    "detail": "keyword",
                })
        for bi in builtins:
            if bi.startswith(partial) and bi != partial:
                items.append({
                    "label": bi,
                    "kind": 3,  # Function
                    "detail": "builtin",
                })
        return items

    @staticmethod
    def _symbol_kind(sym_type: str) -> int:
        """将符号类型映射到 LSP CompletionItemKind"""
        kind_map = {
            "class": 7,      # Class
            "function": 3,   # Function
            "method": 2,     # Method
            "variable": 6,   # Variable
            "import": 9,     # Module
        }
        return kind_map.get(sym_type, 1)  # Text

    # ── Hover ──────────────────────────────

    def _handle_hover(self, params: dict) -> dict | None:
        """处理 textDocument/hover — 悬停显示符号信息"""
        uri = params.get("textDocument", {}).get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)

        text = self._documents.get(uri, "")
        if not text:
            return None

        # 获取光标处的单词
        lines = text.split("\n")
        if line >= len(lines):
            return None
        current_line = lines[line]
        word = self._get_word_at(current_line, character)
        if not word:
            return None

        # 在符号缓存中查找
        symbols = self._symbol_cache.get(uri, [])
        for sym in symbols:
            if sym.get("name") == word:
                hover_text = self._format_hover(sym, text)
                if hover_text:
                    return {
                        "contents": {
                            "kind": "markdown",
                            "value": hover_text,
                        },
                    }
        return None

    def _format_hover(self, sym: dict, full_text: str) -> str:
        """格式化悬停信息为 Markdown"""
        sym_type = sym.get("type", "")
        name = sym.get("name", "")
        detail = sym.get("detail", "")
        doc = sym.get("doc", "")

        parts = []
        if detail:
            parts.append(f"```python\n{detail}\n```")
        elif sym_type == "class":
            parts.append(f"```python\nclass {name}\n```")
        elif sym_type in ("function", "method"):
            parts.append(f"```python\ndef {name}(...)\n```")

        # 尝试从 AST 提取 docstring
        if not doc and sym.get("line"):
            doc = self._extract_docstring(full_text, sym["line"])
        if doc:
            parts.append(f"---\n{doc}")

        parent = sym.get("parent")
        if parent:
            parts.append(f"*Defined in class `{parent}`*")

        return "\n\n".join(parts) if parts else ""

    def _extract_docstring(self, text: str, lineno: int) -> str:
        """从源码中提取指定行定义的 docstring"""
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if hasattr(node, "lineno") and node.lineno == lineno:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if (node.body and isinstance(node.body[0], ast.Expr)
                                and isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                            val = node.body[0].value
                            return val.s if isinstance(val, ast.Str) else str(val.value)
        except (SyntaxError, ValueError):
            pass
        return ""

    @staticmethod
    def _get_word_at(line: str, col: int) -> str:
        """提取指定列位置的单词"""
        if col > len(line):
            col = len(line)
        # 向左扩展
        start = col
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1
        # 向右扩展
        end = col
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1
        return line[start:end] if start < end else ""

    # ── Go-to-Definition ──────────────────────────────

    def _handle_definition(self, params: dict) -> list[dict] | None:
        """处理 textDocument/definition — 跳转到定义"""
        uri = params.get("textDocument", {}).get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)

        text = self._documents.get(uri, "")
        if not text:
            return None

        lines = text.split("\n")
        if line >= len(lines):
            return None
        word = self._get_word_at(lines[line], character)
        if not word:
            return None

        # 在当前文件的符号中搜索
        symbols = self._symbol_cache.get(uri, [])
        for sym in symbols:
            if sym.get("name") == word and sym.get("line"):
                return [{
                    "uri": uri,
                    "range": {
                        "start": {"line": sym["line"] - 1, "character": 0},
                        "end": {"line": sym["line"] - 1, "character": len(word)},
                    },
                }]

        # 搜索其他已打开文档
        for other_uri, other_symbols in self._symbol_cache.items():
            if other_uri == uri:
                continue
            for sym in other_symbols:
                if sym.get("name") == word and sym.get("line"):
                    return [{
                        "uri": other_uri,
                        "range": {
                            "start": {"line": sym["line"] - 1, "character": 0},
                            "end": {"line": sym["line"] - 1, "character": len(word)},
                        },
                    }]

        return None

    # ── Diagnostics ──────────────────────────────

    def _publish_diagnostics(self, uri: str, text: str):
        """发布诊断信息（语法错误 + 基础 lint）"""
        diagnostics = []

        # 1. Python 语法错误
        try:
            ast.parse(text)
        except SyntaxError as e:
            diagnostics.append({
                "range": {
                    "start": {"line": (e.lineno or 1) - 1, "character": (e.offset or 1) - 1},
                    "end": {"line": (e.lineno or 1) - 1, "character": (e.offset or 1)},
                },
                "severity": 1,  # Error
                "source": "turing-lsp",
                "message": f"SyntaxError: {e.msg}",
            })

        # 2. 基础 lint 检查
        lines = text.split("\n")
        for i, line_text in enumerate(lines):
            # 未使用的 import（简易检测：import 行中的名称在后续未出现）
            # 这里只做简单的行级检查
            stripped = line_text.rstrip()

            # 检查行过长（PEP 8: 120 字符警告）
            if len(stripped) > 120:
                diagnostics.append({
                    "range": {
                        "start": {"line": i, "character": 120},
                        "end": {"line": i, "character": len(stripped)},
                    },
                    "severity": 3,  # Information
                    "source": "turing-lsp",
                    "message": f"Line too long ({len(stripped)} > 120 characters)",
                    "code": "E501",
                })

            # 检查行尾空白
            if stripped != line_text and line_text.endswith(" "):
                diagnostics.append({
                    "range": {
                        "start": {"line": i, "character": len(stripped)},
                        "end": {"line": i, "character": len(line_text)},
                    },
                    "severity": 4,  # Hint
                    "source": "turing-lsp",
                    "message": "Trailing whitespace",
                    "code": "W291",
                })

        self._diagnostics_cache[uri] = diagnostics

        # 发送 publishDiagnostics 通知
        notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": diagnostics,
            },
        }
        self._write_message(notification)

    # ── Code Actions ──────────────────────────────

    def _handle_code_action(self, params: dict) -> list[dict]:
        """处理 textDocument/codeAction — 提供快速修复"""
        uri = params.get("textDocument", {}).get("uri", "")
        context = params.get("context", {})
        diagnostics = context.get("diagnostics", [])

        actions = []
        for diag in diagnostics:
            code = diag.get("code", "")

            if code == "W291":
                # 行尾空白修复
                line = diag["range"]["start"]["line"]
                text = self._documents.get(uri, "")
                lines = text.split("\n")
                if line < len(lines):
                    stripped = lines[line].rstrip()
                    actions.append({
                        "title": "Remove trailing whitespace",
                        "kind": "quickfix",
                        "diagnostics": [diag],
                        "edit": {
                            "changes": {
                                uri: [{
                                    "range": {
                                        "start": {"line": line, "character": 0},
                                        "end": {"line": line, "character": len(lines[line])},
                                    },
                                    "newText": stripped,
                                }],
                            },
                        },
                    })

        # 通用：Organize Imports（使用 isort 或内置排序）
        text = self._documents.get(uri, "")
        if text and "import " in text:
            actions.append({
                "title": "Organize imports (sort)",
                "kind": "source.organizeImports",
                "command": {
                    "title": "Organize Imports",
                    "command": "turing.organizeImports",
                    "arguments": [uri],
                },
            })

        return actions


def main():
    """LSP 服务器入口"""
    server = TuringLSPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
