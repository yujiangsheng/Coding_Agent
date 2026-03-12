"""持久记忆（L3）

四层记忆系统的第三层，结构化的核心知识库：
- 按项目和主题组织的 YAML/JSON 文件
- 包括：项目架构知识、策略模板、进化日志、通用索引
- 永久保存，仅显式更新
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml


class PersistentMemory:
    """第三层记忆 —— 持久记忆

    - 结构化的核心知识和规则
    - 按项目和主题组织的 YAML/JSON 文件
    - 永久保存，仅显式更新
    """

    def __init__(self, data_dir: str = "turing_data"):
        self._base = Path(data_dir) / "persistent_memory"
        self._projects_dir = self._base / "projects"
        self._strategies_dir = self._base / "strategies"
        self._base.mkdir(parents=True, exist_ok=True)
        self._projects_dir.mkdir(exist_ok=True)
        self._strategies_dir.mkdir(exist_ok=True)

        # 通用持久记忆索引文件
        self._index_path = self._base / "index.json"
        self._index = self._load_index()

    def add(self, content: Any, tags: list[str] | None = None, metadata: dict | None = None) -> dict:
        """写入一条持久记忆（自动去重）"""
        entry_id = uuid.uuid4().hex[:12]
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)

        # 去重检查：如果已有高度相似的条目则跳过
        if self._is_duplicate(text):
            return {"status": "skipped", "reason": "duplicate", "layer": "persistent"}

        entry = {
            "id": entry_id,
            "content": text,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._index.append(entry)
        self._save_index()
        return {"status": "ok", "id": entry_id, "layer": "persistent"}

    def _is_duplicate(self, text: str, threshold: float = 0.85) -> bool:
        """检查新内容是否与已有条目高度相似（基于 Jaccard 相似度）"""
        if not self._index:
            return False
        new_tokens = set(text.lower().split())
        if len(new_tokens) < 3:
            # 太短的内容按精确匹配
            return any(e["content"].strip() == text.strip() for e in self._index[-100:])
        for entry in self._index[-100:]:  # 只检查最近 100 条
            old_tokens = set(entry["content"].lower().split())
            if not old_tokens:
                continue
            intersection = new_tokens & old_tokens
            union = new_tokens | old_tokens
            similarity = len(intersection) / len(union) if union else 0
            if similarity >= threshold:
                return True
        return False

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

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """TF-IDF 风格检索持久记忆"""
        import math
        query_words = self._tokenize(query)
        if not query_words:
            return []

        # 构建候选池：索引条目 + 策略文件
        candidates = []
        for entry in self._index:
            candidates.append({
                "id": entry.get("id", ""),
                "content": entry["content"],
                "tags": entry.get("tags", []),
                "text_for_search": entry["content"].lower() + " " + " ".join(entry.get("tags", [])).lower(),
            })

        for strategy_file in self._strategies_dir.glob("*.yaml"):
            try:
                with open(strategy_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                full_text = yaml.dump(data, allow_unicode=True)
                candidates.append({
                    "id": strategy_file.stem,
                    "content": full_text,
                    "tags": ["strategy"],
                    "text_for_search": full_text.lower(),
                })
            except Exception:
                continue

        if not candidates:
            return []

        # 计算 IDF
        n_docs = len(candidates)
        doc_freq = {}
        for c in candidates:
            text = c["text_for_search"]
            seen = set()
            for w in query_words:
                if w in text and w not in seen:
                    doc_freq[w] = doc_freq.get(w, 0) + 1
                    seen.add(w)

        scored = []
        for c in candidates:
            text = c["text_for_search"]
            score = 0.0
            for w in query_words:
                if w in text:
                    tf = text.count(w)
                    idf = math.log(1 + n_docs / (1 + doc_freq.get(w, 0)))
                    score += tf * idf
            if score > 0:
                scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": c["id"],
                "content": c["content"][:500],
                "tags": c["tags"],
                "layer": "persistent",
            }
            for _, c in scored[:top_k]
        ]

    # --- 项目知识管理 ---

    def save_project_info(self, project_name: str, info_type: str, data: dict):
        """保存项目级知识"""
        project_dir = self._projects_dir / project_name
        project_dir.mkdir(exist_ok=True)
        filepath = project_dir / f"{info_type}.yaml"
        # v11.0: 原子写入
        import tempfile, os
        content = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        fd, tmp_path = tempfile.mkstemp(dir=str(filepath.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(filepath))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load_project_info(self, project_name: str, info_type: str) -> dict | None:
        """加载项目级知识"""
        filepath = self._projects_dir / project_name / f"{info_type}.yaml"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return None

    def list_projects(self) -> list[str]:
        return [d.name for d in self._projects_dir.iterdir() if d.is_dir()]

    # --- 策略模板管理 ---

    def save_strategy(self, task_type: str, strategy: dict):
        """保存/更新策略模板"""
        filepath = self._strategies_dir / f"{task_type}.yaml"
        strategy["updated_at"] = time.time()
        # v11.0: 原子写入
        import tempfile, os
        content = yaml.dump(strategy, allow_unicode=True, default_flow_style=False)
        fd, tmp_path = tempfile.mkstemp(dir=str(filepath.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(filepath))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load_strategy(self, task_type: str) -> dict | None:
        """加载策略模板"""
        filepath = self._strategies_dir / f"{task_type}.yaml"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return None

    def list_strategies(self) -> list[str]:
        return [f.stem for f in self._strategies_dir.glob("*.yaml")]

    # --- 进化日志 ---

    def get_evolution_log(self) -> list[dict]:
        log_path = self._base / "evolution_log.json"
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def append_evolution_log(self, entry: dict):
        log = self.get_evolution_log()
        log.append(entry)
        log_path = self._base / "evolution_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    # --- 内部 ---

    _SCHEMA_VERSION = 2  # 当前索引 schema 版本

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 索引损坏：备份后重建
            backup = self._index_path.with_suffix(".json.bak")
            try:
                import shutil
                shutil.copy2(self._index_path, backup)
            except Exception:
                pass
            return []

        # schema 版本迁移
        if isinstance(data, dict) and "schema_version" in data:
            return self._migrate_index(data)
        elif isinstance(data, list):
            # v1（无版本号）→ v2：补充缺失字段
            migrated = []
            for entry in data:
                if not isinstance(entry, dict) or "content" not in entry:
                    continue  # 跳过损坏条目
                entry.setdefault("id", uuid.uuid4().hex[:12])
                entry.setdefault("tags", [])
                entry.setdefault("metadata", {})
                entry.setdefault("created_at", 0)
                entry.setdefault("updated_at", entry.get("created_at", 0))
                migrated.append(entry)
            return migrated
        return []

    def _migrate_index(self, data: dict) -> list[dict]:
        """运行 schema 版本迁移"""
        version = data.get("schema_version", 1)
        entries = data.get("entries", [])
        # 未来版本迁移逻辑放在这里
        return entries

    def _save_index(self):
        data = {
            "schema_version": self._SCHEMA_VERSION,
            "entries": self._index,
        }
        # 原子写入：先写临时文件再重命名，防止中途崩溃损坏
        tmp_path = self._index_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self._index_path)
