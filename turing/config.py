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

import logging
import os
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

# 配置 schema：定义合法的顶层和二层 key 以及值类型约束
_CONFIG_SCHEMA = {
    "model": {"name": str, "temperature": (int, float), "reflect_temperature": (int, float),
              "max_iterations": int, "token_budget": int},
    "memory": {"data_dir": str, "working": dict, "long_term": dict, "persistent": dict},
    "output": {"generated_code_dir": str},
    "evolution": {"strategy_threshold": int, "distill_interval": int},
    "security": {"confirmation_mode": str, "auto_approve": bool, "sandbox_mode": str,
                 "docker_image": str, "blocked_commands": list, "blocked_paths": list,
                 "workspace_root": str},
    "providers": dict,  # 动态 provider 配置
    "router": dict,     # 路由配置
}

_DEFAULT_CONFIG = {
    "model": {
        "name": "qwen3-coder:30b",
        "temperature": 0.3,
        "reflect_temperature": 0.6,
        "max_iterations": 50,
        "token_budget": 0,  # 0 = 无限制; >0 = 单任务最大 token 预算
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
    "output": {"generated_code_dir": "generated_code"},
    "evolution": {"strategy_threshold": 5, "distill_interval": 50},
    "security": {
        "confirmation_mode": "interactive",
        "auto_approve": False,
        "sandbox_mode": "host",
        "docker_image": "python:3.11-slim",
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
            # 验证配置
            self._validate(file_data)
            data = _deep_merge(data, file_data)

        self._data = data
        # 解析 workspace_root
        ws = data["security"]["workspace_root"]
        if not ws:
            self._data["security"]["workspace_root"] = os.getcwd()

    @staticmethod
    def _validate(file_data: dict):
        """验证用户配置文件中的 key 和值类型，打印警告"""
        for top_key, value in file_data.items():
            if top_key not in _CONFIG_SCHEMA:
                logger.warning("配置警告: 未知的顶层配置项 '%s'，将被忽略", top_key)
                continue
            schema_val = _CONFIG_SCHEMA[top_key]
            if isinstance(schema_val, dict) and isinstance(value, dict):
                for sub_key, sub_val in value.items():
                    if sub_key in schema_val:
                        expected_type = schema_val[sub_key]
                        if isinstance(expected_type, tuple):
                            if not isinstance(sub_val, expected_type):
                                logger.warning(
                                    "配置警告: '%s.%s' 应为 %s 类型，实际为 %s",
                                    top_key, sub_key,
                                    "/".join(t.__name__ for t in expected_type),
                                    type(sub_val).__name__,
                                )
                        elif expected_type is not dict and not isinstance(sub_val, expected_type):
                            logger.warning(
                                "配置警告: '%s.%s' 应为 %s 类型，实际为 %s",
                                top_key, sub_key, expected_type.__name__,
                                type(sub_val).__name__,
                            )

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
        """加载配置单例，首次调用时初始化，后续调用返回同一实例。"""
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例，下次 load() 将重新初始化。主要用于测试。"""
        cls._instance = None
