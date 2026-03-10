"""长期记忆（L2）

四层记忆系统的第二层，基于向量数据库的跨会话经验知识库：
- 主存储：ChromaDB 向量数据库，支持语义检索（cosine 相似度）
- 降级方案：当 ChromaDB 未安装时，自动回退到 JSON 文件 + 关键词匹配
- 访问计数：每次检索多的记忆会增加访问计数，支持按访问频率淘汰
- 存储内容：情景记忆、任务反思、用户偏好、编程知识
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import chromadb
    from chromadb.config import Settings

    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class LongTermMemory:
    """第二层记忆 —— 长期记忆

    - 跨会话经验知识库
    - 基于 ChromaDB 向量数据库，支持语义检索
    - 包含情景记忆、语义记忆、用户偏好
    """

    def __init__(self, data_dir: str = "turing_data", collection_name: str = "turing_long_term"):
        self._data_dir = Path(data_dir) / "long_term_memory"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._collection_name = collection_name

        if HAS_CHROMADB:
            self._client = chromadb.PersistentClient(
                path=str(self._data_dir / "chroma_db")
            )
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            # 降级方案：基于 JSON 文件的简单存储
            self._json_path = self._data_dir / "fallback_store.json"
            self._store = self._load_json_store()

    def add(self, content: Any, tags: list[str] | None = None, metadata: dict | None = None) -> dict:
        """写入一条长期记忆"""
        doc_id = uuid.uuid4().hex[:12]
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        meta = {
            "tags": json.dumps(tags or []),
            "timestamp": time.time(),
            "access_count": 0,
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v

        if HAS_CHROMADB:
            self._collection.add(
                documents=[text],
                metadatas=[meta],
                ids=[doc_id],
            )
        else:
            self._store.append({"id": doc_id, "content": text, "metadata": meta})
            self._save_json_store()

        return {"status": "ok", "id": doc_id, "layer": "long_term"}

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索长期记忆"""
        if HAS_CHROMADB:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, max(self._collection.count(), 1)),
            )
            items = []
            if results["documents"] and results["documents"][0]:
                for doc, meta, doc_id in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["ids"][0],
                ):
                    # 更新访问计数
                    self._collection.update(
                        ids=[doc_id],
                        metadatas=[{**meta, "access_count": meta.get("access_count", 0) + 1}],
                    )
                    items.append({
                        "id": doc_id,
                        "content": doc,
                        "tags": json.loads(meta.get("tags", "[]")),
                        "layer": "long_term",
                    })
            return items
        else:
            # 降级：关键词匹配
            return self._search_json(query, top_k)

    def count(self) -> int:
        if HAS_CHROMADB:
            return self._collection.count()
        return len(self._store)

    def delete_old(self, max_age_days: int = 90, min_access: int = 0):
        """淘汰旧的、低访问的记忆"""
        if not HAS_CHROMADB:
            return
        cutoff = time.time() - max_age_days * 86400
        results = self._collection.get(
            where={"timestamp": {"$lt": cutoff}},
        )
        if results["ids"]:
            ids_to_delete = []
            for i, meta in enumerate(results["metadatas"]):
                if meta.get("access_count", 0) <= min_access:
                    ids_to_delete.append(results["ids"][i])
            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)

    # --- JSON fallback ---

    def _load_json_store(self) -> list[dict]:
        if self._json_path.exists():
            with open(self._json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_json_store(self):
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import re
        tokens = []
        for word in text.lower().split():
            if len(word) > 1:
                tokens.append(word)
        cn_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for seg in cn_chars:
            if len(seg) >= 2:
                for i in range(len(seg) - 1):
                    tokens.append(seg[i:i+2])
            if len(seg) == 1:
                tokens.append(seg)
        return list(set(tokens)) if tokens else [text.lower().strip()]

    def _search_json(self, query: str, top_k: int) -> list[dict]:
        """TF-IDF 风格的关键词匹配（含时间衰减）"""
        import math
        query_words = self._tokenize(query)
        if not query_words:
            return []

        n_docs = len(self._store)
        doc_freq = {}
        for item in self._store:
            text = item["content"].lower()
            seen = set()
            for w in query_words:
                if w in text and w not in seen:
                    doc_freq[w] = doc_freq.get(w, 0) + 1
                    seen.add(w)

        scored = []
        for item in self._store:
            text = item["content"].lower()
            score = 0.0
            for w in query_words:
                if w in text:
                    tf = text.count(w)
                    idf = math.log(1 + n_docs / (1 + doc_freq.get(w, 0)))
                    score += tf * idf
            # 时间衰减
            ts = item.get("metadata", {}).get("timestamp", 0)
            age_days = (time.time() - ts) / 86400 if ts else 30
            recency_boost = 1.0 / (1.0 + age_days * 0.005)
            score *= recency_boost
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": item["id"],
                "content": item["content"],
                "tags": json.loads(item["metadata"].get("tags", "[]")),
                "layer": "long_term",
            }
            for _, item in scored[:top_k]
        ]
