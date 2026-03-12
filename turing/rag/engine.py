"""检索增强生成（RAG）引擎

四层记忆系统中 L4 外部记忆的核心组件，基于 ChromaDB 实现：
- 支持三种文档源：docs（本地文档）、codebase（代码库）、experience_db（经验库）
- 内置文本分块策略，按段落分割
- 通过 /index 命令或 index_directory() 批量索引项目文件

当 ChromaDB 未安装时，搜索返回空结果并提示安装。
"""

from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class RAGEngine:
    """RAG（检索增强生成）引擎

    支持三种文档源：
    - docs: 本地文档库（Markdown/TXT/RST）
    - codebase: 代码库索引
    - experience_db: 经验知识库
    """

    def __init__(self, data_dir: str = "turing_data"):
        self._data_dir = Path(data_dir) / "external_memory"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._docs_dir = self._data_dir / "docs"
        self._docs_dir.mkdir(exist_ok=True)
        self._hash_store_path = self._data_dir / "file_hashes.json"
        self._file_hashes: dict[str, str] = self._load_hashes()

        if HAS_CHROMADB:
            self._client = chromadb.PersistentClient(
                path=str(self._data_dir / "rag_db")
            )
            self._collections = {}
        else:
            self._collections = {}

    def _load_hashes(self) -> dict[str, str]:
        """加载文件哈希缓存"""
        if self._hash_store_path.exists():
            try:
                return json.loads(self._hash_store_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_hashes(self):
        """持久化文件哈希缓存"""
        self._hash_store_path.write_text(
            json.dumps(self._file_hashes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _file_hash(self, filepath: str) -> str:
        """计算文件内容哈希"""
        h = hashlib.sha256()
        p = Path(filepath)
        if not p.exists():
            return ""
        h.update(p.read_bytes())
        return h.hexdigest()[:16]

    def _get_collection(self, source: str):
        """获取或创建指定 source 的 ChromaDB collection。"""
        if not HAS_CHROMADB:
            return None
        if source not in self._collections:
            self._collections[source] = self._client.get_or_create_collection(
                name=f"rag_{source}",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[source]

    def index_file(self, filepath: str, source: str = "docs", chunk_size: int = 500):
        """将文件分块索引到 RAG 库（增量：跳过未变更文件）"""
        if not HAS_CHROMADB:
            return {"error": "ChromaDB 未安装，RAG 不可用"}

        p = Path(filepath)
        if not p.exists():
            return {"error": f"文件不存在: {filepath}"}

        # 增量检查：文件未变更则跳过
        current_hash = self._file_hash(filepath)
        cache_key = f"{source}:{filepath}"
        if cache_key in self._file_hashes and self._file_hashes[cache_key] == current_hash:
            return {"status": "skipped", "reason": "unchanged", "file": filepath}

        text = p.read_text(encoding="utf-8", errors="replace")
        chunks = self._split_text(text, chunk_size)
        collection = self._get_collection(source)

        ids = []
        for i, chunk in enumerate(chunks):
            doc_id = hashlib.md5(f"{filepath}:{i}".encode()).hexdigest()[:12]
            collection.upsert(
                documents=[chunk],
                metadatas=[{"source_file": filepath, "chunk_index": i}],
                ids=[doc_id],
            )
            ids.append(doc_id)

        # 更新哈希缓存
        self._file_hashes[cache_key] = current_hash
        self._save_hashes()

        return {"status": "ok", "chunks_indexed": len(chunks), "file": filepath}

    def index_directory(self, dirpath: str, source: str = "docs",
                        extensions: list[str] = None):
        """增量索引整个目录（仅重索引变更文件）"""
        if extensions is None:
            extensions = [".md", ".txt", ".rst", ".py", ".js", ".ts", ".yaml", ".yml"]
        p = Path(dirpath)
        if not p.is_dir():
            return {"error": f"目录不存在: {dirpath}"}

        indexed = 0
        skipped = 0
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        for ext in extensions:
            for fp in p.rglob(f"*{ext}"):
                if any(part in skip_dirs for part in fp.relative_to(p).parts):
                    continue
                result = self.index_file(str(fp), source)
                if result.get("status") == "skipped":
                    skipped += 1
                else:
                    indexed += 1
        return {"status": "ok", "files_indexed": indexed, "files_skipped": skipped}

    def remove_file_from_index(self, filepath: str, source: str = "docs") -> dict:
        """从 RAG 索引中删除指定文件的所有分块（v3.1）"""
        if not HAS_CHROMADB:
            return {"error": "ChromaDB 未安装，RAG 不可用"}

        collection = self._get_collection(source)
        if collection is None:
            return {"error": f"集合 '{source}' 不存在"}

        # 查找该文件的所有 chunk IDs
        try:
            results = collection.get(
                where={"source_file": filepath},
            )
            ids_to_delete = results.get("ids", [])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
        except Exception:
            # Fallback: 用 ID 前缀匹配暴力删除
            ids_to_delete = []

        # 清除哈希缓存
        cache_key = f"{source}:{filepath}"
        removed_hash = self._file_hashes.pop(cache_key, None)
        if removed_hash or ids_to_delete:
            self._save_hashes()

        return {
            "status": "ok",
            "file": filepath,
            "chunks_removed": len(ids_to_delete),
        }

    def search(self, query: str, source: str = "docs", top_k: int = 5) -> dict:
        """在 RAG 库中搜索（支持查询扩展）"""
        if not HAS_CHROMADB:
            return {"results": [], "message": "ChromaDB 未安装，RAG 不可用"}

        collection = self._get_collection(source)
        if collection.count() == 0:
            return {"results": [], "message": f"RAG 库 '{source}' 为空，请先索引文档"}

        # 查询扩展：将原始查询拆分为多个搜索词
        expanded_queries = self._expand_query(query)
        all_items = {}

        for q in expanded_queries:
            results = collection.query(
                query_texts=[q],
                n_results=min(top_k, collection.count()),
            )
            if results["documents"] and results["documents"][0]:
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results.get("distances", [[]])[0] or [1.0] * len(results["documents"][0]),
                ):
                    key = f"{meta.get('source_file', '')}:{meta.get('chunk_index', 0)}"
                    if key not in all_items or dist < all_items[key]["_dist"]:
                        all_items[key] = {
                            "content": doc,
                            "source_file": meta.get("source_file", ""),
                            "chunk_index": meta.get("chunk_index", 0),
                            "_dist": dist,
                        }

        # 按相似度排序，去除内部距离字段
        sorted_items = sorted(all_items.values(), key=lambda x: x["_dist"])[:top_k]
        items = [{k: v for k, v in it.items() if k != "_dist"} for it in sorted_items]

        return {"results": items, "count": len(items)}

    def _expand_query(self, query: str) -> list[str]:
        """查询扩展：生成多个搜索变体以提高召回率"""
        queries = [query]

        # 编程术语同义映射
        synonyms = {
            "function": ["def", "method", "func"],
            "class": ["class", "struct", "type"],
            "error": ["exception", "bug", "fail", "error"],
            "test": ["test", "spec", "unittest"],
            "import": ["import", "require", "include", "from"],
            "variable": ["var", "let", "const", "variable"],
            "修复": ["fix", "修复", "repair"],
            "函数": ["function", "def", "函数", "方法"],
            "错误": ["error", "错误", "异常", "bug"],
            "测试": ["test", "测试", "unittest"],
        }

        words = query.lower().split()
        for word in words:
            if word in synonyms:
                for syn in synonyms[word]:
                    expanded = query.replace(word, syn)
                    if expanded != query and expanded not in queries:
                        queries.append(expanded)
                        break  # 每个词只扩展一次

        return queries[:3]  # 最多 3 个查询变体

    def _split_text(self, text: str, chunk_size: int = 500) -> list[str]:
        """将文本智能分块（代码文件按函数/类边界，文档按段落）"""
        # 代码文件：按函数/类定义边界分块
        if any(marker in text for marker in ["def ", "class ", "function ", "const ", "import "]):
            return self._split_code(text, chunk_size)
        # 文档：按段落分块
        return self._split_paragraphs(text, chunk_size)

    def _split_paragraphs(self, text: str, chunk_size: int) -> list[str]:
        """按段落分块"""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current += "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks or [text[:chunk_size]]

    def _split_code(self, text: str, chunk_size: int) -> list[str]:
        """按函数/类定义边界分块（保持语义完整性）"""
        import re
        # 匹配顶层定义（Python def/class，JS function/class/const）
        boundary_pattern = re.compile(
            r'^(?:def |class |async def |function |export (?:default )?(?:function |class ))',
            re.MULTILINE,
        )
        matches = list(boundary_pattern.finditer(text))

        if not matches:
            return self._split_paragraphs(text, chunk_size)

        chunks = []
        # 文件头部（imports 等）作为一个块
        if matches[0].start() > 0:
            header = text[:matches[0].start()].strip()
            if header:
                chunks.append(header)

        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start:end].strip()
            if len(block) > chunk_size * 2:
                # 超大块按行分割
                lines = block.split("\n")
                sub = ""
                for line in lines:
                    if len(sub) + len(line) > chunk_size and sub:
                        chunks.append(sub.strip())
                        sub = line + "\n"
                    else:
                        sub += line + "\n"
                if sub.strip():
                    chunks.append(sub.strip())
            elif block:
                chunks.append(block)

        return chunks or [text[:chunk_size]]
