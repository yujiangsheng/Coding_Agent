"""外部记忆工具

- rag_search — 基于 RAG 的本地文档检索（依赖 ChromaDB，无则降级）
- web_search — 通过 DuckDuckGo 搜索外部信息
- fetch_url — 获取指定 URL 的网页内容（v3.3）

全局 RAGEngine 实例在 Agent 启动时通过 ``set_rag_engine()`` 注入。
"""

from __future__ import annotations

from turing.tools.registry import tool

# 全局引用，agent 启动时注入
_rag_engine = None


def set_rag_engine(engine):
    """注入全局 RAGEngine 实例（Agent 启动时调用）。"""
    global _rag_engine
    _rag_engine = engine


@tool(
    name="rag_search",
    description="通过 RAG 在本地知识库中搜索相关信息。source 可选: docs（文档）、codebase（代码库）、experience_db（经验库）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "source": {
                "type": "string",
                "description": "文档源: docs / codebase / experience_db",
                "enum": ["docs", "codebase", "experience_db"],
            },
            "top_k": {
                "type": "integer",
                "description": "返回条数，默认5",
            },
        },
        "required": ["query"],
    },
)
def rag_search(query: str, source: str = "docs", top_k: int = 5) -> dict:
    """通过 RAG 引擎在本地知识库中检索相关文档片段。"""
    if _rag_engine is None:
        return {"error": "RAG 引擎未初始化"}
    return _rag_engine.search(query, source, top_k)


@tool(
    name="rag_remove_file",
    description="从 RAG 索引中删除指定文件的所有分块。当文件被删除或需要重建索引时使用。",
    parameters={
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "要从索引中移除的文件路径"},
            "source": {
                "type": "string",
                "description": "文档源 (docs/codebase/experience_db)，默认 docs",
            },
        },
        "required": ["filepath"],
    },
)
def rag_remove_file(filepath: str, source: str = "docs") -> dict:
    """从 RAG 索引中移除指定文件。"""
    if _rag_engine is None:
        return {"error": "RAG 引擎未初始化"}
    return _rag_engine.remove_file_from_index(filepath, source)


@tool(
    name="web_search",
    description="通过搜索引擎查找外部信息（文档、最佳实践、API 参考等）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "max_results": {
                "type": "integer",
                "description": "最大结果数，默认5",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> dict:
    """通过 DuckDuckGo 搜索外部信息并返回结果列表。"""
    # 输入验证
    if not query or not query.strip():
        return {"error": "查询不能为空", "results": []}
    query = query.strip()[:500]  # 截断过长查询
    max_results = max(1, min(max_results, 20))  # 限制 1-20

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return {
            "error": "duckduckgo-search 未安装。请运行: pip install duckduckgo-search",
            "results": [],
        }

    last_error = None
    for attempt in range(2):
        try:
            with DDGS(timeout=10) as ddgs:
                results = []
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
                return {"results": results, "count": len(results)}
        except Exception as e:
            last_error = e
            if attempt == 0:
                import time as _t
                _t.sleep(1)  # 重试前等待

    return {"error": f"搜索失败（重试后）: {last_error}", "results": []}


@tool(
    name="fetch_url",
    description="获取指定 URL 的网页内容，自动提取正文文本。适用于阅读文档、API 参考、技术博客等。",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的 URL 地址"},
            "max_length": {
                "type": "integer",
                "description": "返回内容的最大字符数，默认 8000",
            },
        },
        "required": ["url"],
    },
)
def fetch_url(url: str, max_length: int = 8000) -> dict:
    """获取 URL 内容，提取正文文本（v3.3 — 对标 Claude Code 的 URL 阅读能力）。"""
    import re as _re
    import urllib.request
    import urllib.error
    from html.parser import HTMLParser

    # 入参验证
    if not url or not url.strip():
        return {"error": "URL 不能为空"}
    url = url.strip()
    max_length = max(500, min(max_length, 50000))

    # 安全: 仅允许 http/https 协议，阻止 SSRF
    if not url.startswith(("http://", "https://")):
        return {"error": "仅支持 http/https 协议"}

    # 安全: 阻止内网地址（SSRF 防护）
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.startswith("172."):
        return {"error": "不允许访问内网地址"}

    class _TextExtractor(HTMLParser):
        """简易 HTML 正文提取器"""
        def __init__(self):
            super().__init__()
            self._text: list[str] = []
            self._skip = False
            self._skip_tags = {"script", "style", "noscript", "svg", "head"}

        def handle_starttag(self, tag, attrs):
            if tag in self._skip_tags:
                self._skip = True

        def handle_endtag(self, tag):
            if tag in self._skip_tags:
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                text = data.strip()
                if text:
                    self._text.append(text)

        def get_text(self) -> str:
            return "\n".join(self._text)

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Turing-Agent/1.0 (Coding Assistant)",
            "Accept": "text/html,application/xhtml+xml,text/plain,application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # 限制下载大小 (2MB)
            raw = resp.read(2 * 1024 * 1024)

        # 检测编码
        encoding = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
            if charset:
                encoding = charset

        text = raw.decode(encoding, errors="replace")

        # 对 HTML 内容提取正文
        if "html" in content_type or text.strip().startswith(("<!", "<html", "<HTML")):
            extractor = _TextExtractor()
            extractor.feed(text)
            text = extractor.get_text()
            # 清理多余空行
            text = _re.sub(r"\n{3,}", "\n\n", text)

        # 截断
        if len(text) > max_length:
            text = text[:max_length] + "\n\n... [内容已截断]"

        return {
            "url": url,
            "content_type": content_type.split(";")[0].strip(),
            "length": len(text),
            "content": text,
        }

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP 错误 {e.code}: {e.reason}", "url": url}
    except urllib.error.URLError as e:
        return {"error": f"连接失败: {e.reason}", "url": url}
    except Exception as e:
        return {"error": f"获取失败: {e}", "url": url}
