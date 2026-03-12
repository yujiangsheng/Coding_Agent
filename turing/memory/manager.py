"""记忆统一管理器

为 Turing 提供四层记忆的统一接口：
- L1 工作记忆（WorkingMemory）
- L2 长期记忆（LongTermMemory）
- L3 持久记忆（PersistentMemory）
- L4 外部记忆由 RAGEngine 单独处理

提供 retrieve / write / reflect / compress / format 等操作，
以及跨层去重和统计发布能力。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from turing.memory.working import WorkingMemory
from turing.memory.long_term import LongTermMemory
from turing.memory.persistent import PersistentMemory


def _content_hash(content: str) -> str:
    """生成内容的标准化哈希，用于跨层去重"""
    normalized = content.strip().lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class MemoryManager:
    """Turing 四层记忆管理器

    统一管理工作记忆、长期记忆、持久记忆三个内部层（外部记忆由 RAG 引擎单独处理）。
    提供统一的 retrieve / write / reflect 接口。
    """

    def __init__(self, data_dir: str = "turing_data"):
        self.data_dir = data_dir
        self.working = WorkingMemory(data_dir)
        self.long_term = LongTermMemory(data_dir)
        self.persistent = PersistentMemory(data_dir)

    def retrieve(self, query: str, layers: list[str], top_k: int = 5) -> list[dict]:
        """从指定层检索相关记忆（跨层统一排名）

        Args:
            query: 检索关键词
            layers: 要检索的层 ["working", "long_term", "persistent"]
            top_k: 最终返回的最大条数
        """
        results = []
        layer_map = {
            "working": self.working,
            "long_term": self.long_term,
            "persistent": self.persistent,
        }

        # 层优先级权重：持久 > 长期 > 工作
        layer_weights = {"persistent": 1.2, "long_term": 1.0, "working": 0.8}

        for layer_name in layers:
            store = layer_map.get(layer_name)
            if store:
                # v9.0: 错误隔离，单层失败不影响其他层
                try:
                    # 每层多取一些，后面统一排名
                    items = store.search(query, top_k=top_k * 2)
                except Exception as _layer_err:
                    import logging as _mem_log
                    _mem_log.getLogger(__name__).warning(
                        "记忆层 %s 检索失败，跳过: %s", layer_name, _layer_err
                    )
                    continue
                for i, item in enumerate(items):
                    item["layer"] = layer_name
                    # 基于层权重和检索排名打分
                    item["_rank_score"] = layer_weights.get(layer_name, 1.0) * (1.0 / (1 + i))
                results.extend(items)

        # 去重（按 id + 内容哈希双重去重）
        seen_ids = set()
        seen_hashes = set()
        deduped = []
        for r in results:
            rid = r.get("id", "")
            content = r.get("content", "")
            chash = _content_hash(content) if content else ""

            # ID 去重
            if rid and rid in seen_ids:
                continue
            # 内容哈希去重（跨层不同 ID 但内容相同）
            if chash and chash in seen_hashes:
                continue

            if rid:
                seen_ids.add(rid)
            if chash:
                seen_hashes.add(chash)
            deduped.append(r)

        # 按综合排名分数排序
        deduped.sort(key=lambda x: x.get("_rank_score", 0), reverse=True)

        # 清理内部排名字段
        for r in deduped:
            r.pop("_rank_score", None)

        return deduped[:top_k]

    def write(self, layer: str, content: Any, tags: list[str] | None = None) -> dict:
        """向指定层写入记忆"""
        layer_map = {
            "working": self.working,
            "long_term": self.long_term,
            "persistent": self.persistent,
        }
        store = layer_map.get(layer)
        if store is None:
            return {"error": f"未知记忆层: {layer}"}
        return store.add(content, tags=tags)

    def reflect(self, task_summary: str, outcome: str, lessons: str) -> dict:
        """任务反思：将工作记忆中的经验归纳后存入长期记忆"""
        working_summary = self.working.get_summary()
        reflection = {
            "summary": task_summary,
            "outcome": outcome,
            "lessons": lessons,
            "working_context": working_summary,
            "timestamp": time.time(),
        }
        self.long_term.add(
            json.dumps(reflection, ensure_ascii=False),
            tags=["reflection", outcome],
        )
        return {"status": "ok", "stored_in": "long_term", "reflection": reflection}

    def compress_working_memory(self, keep_recent: int = 5) -> dict:
        """压缩工作记忆：将旧条目摘要后存入长期记忆"""
        old_items = self.working.get_old_items(keep_recent=keep_recent)
        if not old_items:
            return {"status": "no_compression_needed"}

        # 生成摘要
        summary_parts = [item["content"][:200] for item in old_items]
        summary = "工作记忆压缩摘要:\n" + "\n".join(f"- {p}" for p in summary_parts)
        self.long_term.add(summary, tags=["working_memory_overflow"])
        self.working.remove(old_items)
        return {
            "status": "compressed",
            "items_moved": len(old_items),
        }

    def get_stats(self) -> dict:
        """获取记忆系统统计信息"""
        return {
            "working_items": self.working.item_count(),
            "working_chars": self.working.total_chars(),
            "long_term_items": self.long_term.count(),
            "persistent_strategies": len(self.persistent.list_strategies()),
            "persistent_projects": len(self.persistent.list_projects()),
        }

    def format_memories(self, memories: list[dict]) -> str:
        """将检索到的记忆格式化为可注入 Prompt 的文本"""
        if not memories:
            return "（无相关记忆）"
        parts = []
        for m in memories:
            layer = m.get("layer", "unknown")
            tags = ", ".join(m.get("tags", []))
            content = m.get("content", "")[:300]
            parts.append(f"[{layer}]{' (' + tags + ')' if tags else ''}: {content}")
        return "\n".join(parts)

    def cleanup_session(self):
        """清理当前会话的工作记忆"""
        self.working.clear()
