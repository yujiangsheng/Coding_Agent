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

    实现 LSP 的最小子集以提供代码补全能力。
    """

    def __init__(self):
        self._documents: dict[str, str] = {}  # uri -> content
        self._symbol_cache: dict[str, list[dict]] = {}  # uri -> symbols
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
        headers = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            line = line.decode("utf-8").strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        content_length = int(headers.get("Content-Length", 0))
        if content_length == 0:
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
            },
            "serverInfo": {
                "name": "turing-lsp",
                "version": "0.1.0",
            },
        }

    def _handle_did_open(self, params: dict):
        """文档打开通知"""
        doc = params.get("textDocument", {})
        uri = doc.get("uri", "")
        text = doc.get("text", "")
        self._documents[uri] = text
        self._update_symbols(uri, text)

    def _handle_did_change(self, params: dict):
        """文档变更通知"""
        doc = params.get("textDocument", {})
        uri = doc.get("uri", "")
        changes = params.get("contentChanges", [])
        if changes:
            text = changes[-1].get("text", "")
            self._documents[uri] = text
            self._update_symbols(uri, text)

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


def main():
    """LSP 服务器入口"""
    server = TuringLSPServer()
    server.run_stdio()


if __name__ == "__main__":
    main()
