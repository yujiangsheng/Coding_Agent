"""智能模型路由器

根据任务复杂度、token 预算和模型能力自动选择最优 provider，
支持 fallback 链和多模型协同。

路由策略:
- **simple** (复杂度 < 0.3): 使用快速/轻量模型（本地 Ollama 优先）
- **medium** (0.3~0.7): 使用主模型
- **complex** (> 0.7): 使用最强模型（Claude Opus / GPT-4.5 等）

Fallback 链: primary → secondary → fallback，任一失败自动降级。
"""

from __future__ import annotations

import logging
from typing import Any

from turing.llm.provider import LLMProvider, create_provider

logger = logging.getLogger(__name__)


class ModelRouter:
    """根据任务复杂度智能路由到最优 LLM provider"""

    def __init__(self, config: dict | None = None):
        self._providers: dict[str, LLMProvider] = {}
        self._fallback_chain: list[str] = []
        self._routing_rules: dict[str, str] = {}
        self._default: str = ""

        if config:
            self._init_from_config(config)

    def _init_from_config(self, config: dict):
        """从配置中初始化多 provider

        配置格式 (config.yaml)::

            llm:
              default: ollama
              providers:
                ollama:
                  type: ollama
                  model: qwen3-coder:30b
                  context_length: 32768
                openai:
                  type: openai
                  model: gpt-4o
                  api_key: sk-...
                  context_length: 128000
                anthropic:
                  type: anthropic
                  model: claude-sonnet-4-20250514
                  api_key: sk-ant-...
                  context_length: 200000
              routing:
                simple: ollama
                medium: ollama
                complex: openai
              fallback_chain: [openai, anthropic, ollama]
        """
        llm_cfg = config if "providers" in config else config.get("llm", {})

        self._default = llm_cfg.get("default", "ollama")

        # 初始化 providers
        for name, pcfg in llm_cfg.get("providers", {}).items():
            provider_type = pcfg.pop("type", name)
            try:
                self._providers[name] = create_provider(provider_type, **pcfg)
                logger.info(f"已注册 LLM provider: {name} ({provider_type})")
            except Exception as e:
                logger.warning(f"初始化 provider {name} 失败: {e}")
                # 把 type 放回去以防后续重试
                pcfg["type"] = provider_type

        # 路由规则
        self._routing_rules = llm_cfg.get("routing", {
            "simple": self._default,
            "medium": self._default,
            "complex": self._default,
        })

        # Fallback 链
        self._fallback_chain = llm_cfg.get("fallback_chain", [self._default])

        # 如果没有成功初始化任何 provider，创建默认 Ollama
        if not self._providers:
            model_name = config.get("model", {}).get("name", "qwen3-coder:30b")
            self._providers["ollama"] = create_provider("ollama", model=model_name)
            self._default = "ollama"
            self._fallback_chain = ["ollama"]

    def add_provider(self, name: str, provider: LLMProvider):
        """动态注册 provider"""
        self._providers[name] = provider

    def get_provider(self, name: str | None = None) -> LLMProvider:
        """获取指定或默认 provider"""
        key = name or self._default
        if key not in self._providers:
            raise ValueError(f"Provider '{key}' 未注册，已注册: {list(self._providers.keys())}")
        return self._providers[key]

    def _select_provider(self, task_complexity: float = 0.5) -> str:
        """根据任务复杂度选择 provider"""
        if task_complexity < 0.3:
            tier = "simple"
        elif task_complexity < 0.7:
            tier = "medium"
        else:
            tier = "complex"

        selected = self._routing_rules.get(tier, self._default)

        # 如果选中的 provider 不可用，回退到默认
        if selected not in self._providers:
            selected = self._default
        return selected

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        task_complexity: float = 0.5,
        provider_name: str | None = None,
        **kwargs,
    ) -> dict:
        """智能路由聊天请求，支持自动 fallback。

        Args:
            messages: 标准消息列表
            tools: 工具 schema 列表
            temperature: 温度覆盖
            task_complexity: 任务复杂度 [0, 1]
            provider_name: 强制指定 provider（跳过路由）
        """
        if provider_name:
            chain = [provider_name]
        else:
            selected = self._select_provider(task_complexity)
            # 构建 fallback 链：selected → fallback_chain 中其余的
            chain = [selected] + [p for p in self._fallback_chain if p != selected]

        last_error = None
        for name in chain:
            if name not in self._providers:
                continue
            provider = self._providers[name]
            try:
                result = provider.chat(messages, tools=tools, temperature=temperature, **kwargs)
                if name != chain[0]:
                    logger.info(f"已 fallback 到 provider: {name}")
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {name} 调用失败: {e}，尝试 fallback...")

        raise RuntimeError(f"所有 provider 均失败，最后错误: {last_error}")

    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        task_complexity: float = 0.5,
        provider_name: str | None = None,
        **kwargs,
    ) -> dict:
        """流式聊天，逻辑与 chat 相同但调用 stream_chat。"""
        if provider_name:
            chain = [provider_name]
        else:
            selected = self._select_provider(task_complexity)
            chain = [selected] + [p for p in self._fallback_chain if p != selected]

        last_error = None
        for name in chain:
            if name not in self._providers:
                continue
            provider = self._providers[name]
            try:
                result = provider.stream_chat(messages, tools=tools, temperature=temperature, **kwargs)
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {name} stream 失败: {e}，尝试 fallback...")

        raise RuntimeError(f"所有 provider stream 均失败，最后错误: {last_error}")

    def get_context_length(self, provider_name: str | None = None) -> int:
        """获取指定 provider 的上下文窗口大小"""
        provider = self.get_provider(provider_name)
        return provider.context_length

    def list_providers(self) -> list[dict]:
        """列出所有已注册 provider 的信息"""
        return [p.get_info() for p in self._providers.values()]
