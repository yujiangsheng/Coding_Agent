"""工作记忆（L1）

四层记忆系统的第一层，用于存储当前会话的临时上下文：
- 生命周期为会话级，会话结束后自动清除
- 内存中维护，同时落盘到 JSON 文件以防意外中断
- 简单关键词匹配检索（工作记忆量小，无需向量检索）
- 支持标签系统，方便分类管理
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class WorkingMemory:
    """第一层记忆 —— 工作记忆

    - 当前会话的临时上下文
    - 会话结束后自动清除
    - 内存中维护，可落盘到 session 文件
    """

    MAX_ITEMS = 200  # 工作记忆容量上限

    def __init__(self, data_dir: str = "turing_data", max_items: int = None):
        self.session_id = uuid.uuid4().hex[:8]
        self._items: list[dict] = []
        self._max_items = max_items or self.MAX_ITEMS
        self._dir = Path(data_dir) / "working_memory"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # v7.0: 线程安全

    def add(self, content: Any, tags: list[str] | None = None) -> dict:
        """写入一条工作记忆"""
        entry = {
            "id": uuid.uuid4().hex[:12],
            "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
            "tags": tags or [],
            "timestamp": time.time(),
        }
        with self._lock:
            self._items.append(entry)
            # 容量保护：超限时淘汰最老条目
            evicted = 0
            if len(self._items) > self._max_items:
                evicted = len(self._items) - self._max_items
                self._items = self._items[-self._max_items:]
            self._save()
        result = {"status": "ok", "id": entry["id"], "layer": "working"}
        if evicted:
            result["evicted"] = evicted
        return result

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """TF-IDF 风格的关键词检索（兼顾词频和区分度，支持中文）"""
        import math
        import re
        query_words = self._tokenize(query)
        if not query_words or not self._items:
            return []

        # 计算 IDF（逆文档频率）
        n_docs = len(self._items)
        doc_freq = {}  # 每个词出现在多少文档中
        for item in self._items:
            text = item["content"].lower()
            seen = set()
            for w in query_words:
                if w in text and w not in seen:
                    doc_freq[w] = doc_freq.get(w, 0) + 1
                    seen.add(w)

        scored = []
        for item in self._items:
            text = item["content"].lower()
            score = 0.0
            for w in query_words:
                if w in text:
                    tf = text.count(w)
                    idf = math.log(1 + n_docs / (1 + doc_freq.get(w, 0)))
                    score += tf * idf
            # 时间衰减：越新的记忆权重越高
            import time as _t
            age_hours = (_t.time() - item.get("timestamp", 0)) / 3600
            recency_boost = 1.0 / (1.0 + age_hours * 0.01)
            score *= recency_boost
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """分词：空格分割 + 中文字符逐字/双字切分"""
        import re
        tokens = []
        # 先按空格分割
        for word in text.lower().split():
            if len(word) > 1:
                tokens.append(word)
        # 中文字符提取（bigram）
        cn_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for seg in cn_chars:
            if len(seg) >= 2:
                for i in range(len(seg) - 1):
                    tokens.append(seg[i:i+2])
            if len(seg) == 1:
                tokens.append(seg)
        return list(set(tokens)) if tokens else [text.lower().strip()]

    def get_all(self) -> list[dict]:
        return list(self._items)

    def get_summary(self) -> str:
        """获取工作记忆摘要"""
        if not self._items:
            return "（工作记忆为空）"
        parts = []
        for item in self._items[-10:]:  # 最近 10 条
            parts.append(f"- {item['content'][:200]}")
        return "\n".join(parts)

    def get_old_items(self, keep_recent: int = 5) -> list[dict]:
        """获取旧条目（超出 keep_recent 的部分）"""
        if len(self._items) <= keep_recent:
            return []
        return self._items[:-keep_recent]

    def remove(self, items: list[dict]):
        """移除指定条目"""
        ids_to_remove = {item["id"] for item in items}
        with self._lock:
            self._items = [i for i in self._items if i["id"] not in ids_to_remove]
            self._save()

    def clear(self):
        """清空会话"""
        with self._lock:
            self._items.clear()
            session_file = self._dir / f"session_{self.session_id}.json"
            if session_file.exists():
                session_file.unlink()

    def _save(self):
        """原子落盘（v7.0: tmpfile + os.replace 防损坏）"""
        session_file = self._dir / f"session_{self.session_id}.json"
        fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(session_file))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def item_count(self) -> int:
        return len(self._items)

    def total_chars(self) -> int:
        return sum(len(item["content"]) for item in self._items)
