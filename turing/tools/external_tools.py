"""外部记忆工具

- rag_search — 基于 RAG 的本地文档检索（依赖 ChromaDB，无则降级）
- web_search — 通过 DuckDuckGo 搜索外部信息

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
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
            return {"results": results, "count": len(results)}
    except ImportError:
        return {
            "error": "duckduckgo-search 未安装。请运行: pip install duckduckgo-search",
            "results": [],
        }
    except Exception as e:
        return {"error": f"搜索失败: {e}", "results": []}
