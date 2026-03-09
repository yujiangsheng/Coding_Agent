"""配置管理模块

提供 Turing 的全局配置单例，支持：
- YAML 配置文件加载与合并
- 环境变量 TURING_CONFIG 覆盖配置路径
- 点号路径访问（如 config.get('model.name')）
- 默认值兜底，确保所有配置项均有合理初始值

Usage::

    from turing.config import Config
    config = Config.load("config.yaml")
    model_name = config.get("model.name")  # => "qwen3-coder:30b"
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path

_DEFAULT_CONFIG = {
    "model": {
        "name": "qwen3-coder:30b",
        "temperature": 0.3,
        "reflect_temperature": 0.6,
        "max_iterations": 20,
    },
    "memory": {
        "data_dir": "turing_data",
        "working": {"max_context_ratio": 0.3, "keep_recent": 5},
        "long_term": {
            "collection": "turing_long_term",
            "default_top_k": 5,
            "decay_factor": 0.95,
        },
        "persistent": {"dir": "persistent_memory"},
    },
    "evolution": {"strategy_threshold": 5, "distill_interval": 50},
    "security": {
        "blocked_commands": [
            "rm -rf /",
            "rm -rf ~",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",
            "DROP TABLE",
            "DROP DATABASE",
        ],
        "blocked_paths": ["/etc/shadow", "/etc/passwd"],
        "workspace_root": "",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class Config:
    """全局配置单例

    通过 ``Config.load()`` 获取实例（单例模式），
    配置文件中的值会与 ``_DEFAULT_CONFIG`` 深度合并。
    使用 ``Config.reset()`` 重置单例（通常仅用于测试）。
    """

    _instance = None

    def __init__(self, config_path: str | None = None):
        data = _DEFAULT_CONFIG.copy()
        # 尝试加载配置文件
        if config_path is None:
            config_path = os.environ.get("TURING_CONFIG", "config.yaml")
        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                file_data = yaml.safe_load(f) or {}
            data = _deep_merge(data, file_data)

        self._data = data
        # 解析 workspace_root
        ws = data["security"]["workspace_root"]
        if not ws:
            self._data["security"]["workspace_root"] = os.getcwd()

    def get(self, dotpath: str, default=None):
        """通过点号路径获取配置值

        Args:
            dotpath: 以 '.' 分隔的配置路径，如 'model.name'、'security.blocked_commands'
            default: 路径不存在时的默认返回值

        Returns:
            对应的配置值，或 default
        """
        keys = dotpath.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    @classmethod
    def load(cls, config_path: str | None = None) -> "Config":
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None
