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
import re
import time
from collections import defaultdict, deque
from typing import Any

from turing.llm.provider import LLMProvider, create_provider

logger = logging.getLogger(__name__)

# v9.0: 敏感信息清洗正则
_SENSITIVE_RE = re.compile(
    r'(api[_-]?key|apikey|authorization|bearer|secret|token)\s*[:=]\s*\S+',
    re.IGNORECASE,
)


def _scrub_sensitive(text: str) -> str:
    """从错误消息中清除可能泄漏的 API 密钥等敏感信息"""
    return _SENSITIVE_RE.sub(r'\1=***REDACTED***', text)


class _ProviderStats:
    """Provider 性能统计跟踪（v9.0: 增加熔断器）"""

    CIRCUIT_THRESHOLD = 3       # 连续失败次数阈值
    CIRCUIT_COOLDOWN = 60.0     # 熔断器冷却秒数

    def __init__(self, max_history: int = 100):
        self.latencies: deque[float] = deque(maxlen=max_history)
        self.successes: int = 0
        self.failures: int = 0
        self.total_tokens: int = 0
        # v9.0 熔断器状态
        self._consecutive_failures: int = 0
        self._circuit_open_until: float = 0.0

    @property
    def avg_latency(self) -> float:
        return sum(self.latencies) / len(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total > 0 else 1.0

    def record_success(self, latency: float, tokens: int = 0):
        self.latencies.append(latency)
        self.successes += 1
        self.total_tokens += tokens
        self._consecutive_failures = 0   # v9.0: 成功后重置熔断器

    def record_failure(self, latency: float):
        self.latencies.append(latency)
        self.failures += 1
        # v9.0: 熔断器逻辑
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.CIRCUIT_THRESHOLD:
            self._circuit_open_until = time.monotonic() + self.CIRCUIT_COOLDOWN

    def is_circuit_open(self) -> bool:
        """v9.0: 检查熔断器是否处于断开状态"""
        if self._consecutive_failures < self.CIRCUIT_THRESHOLD:
            return False
        if time.monotonic() >= self._circuit_open_until:
            # 冷却期已过，允许半开探测
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "avg_latency_ms": round(self.avg_latency * 1000, 1),
            "p95_latency_ms": round(self.p95_latency * 1000, 1),
            "success_rate": round(self.success_rate, 3),
            "total_calls": self.successes + self.failures,
            "total_tokens": self.total_tokens,
        }


class ModelRouter:
    """根据任务复杂度智能路由到最优 LLM provider"""

    def __init__(self, config: dict | None = None):
        self._providers: dict[str, LLMProvider] = {}
        self._fallback_chain: list[str] = []
        self._routing_rules: dict[str, str] = {}
        self._default: str = ""
        self._stats: dict[str, _ProviderStats] = defaultdict(_ProviderStats)

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
            # v9.0: 不再 pop("type")，避免永久 mutate 原始配置
            provider_type = pcfg.get("type", name)
            init_args = {k: v for k, v in pcfg.items() if k != "type"}
            try:
                self._providers[name] = create_provider(provider_type, **init_args)
                logger.info(f"已注册 LLM provider: {name} ({provider_type})")
            except Exception as e:
                safe_msg = _scrub_sensitive(str(e))
                logger.warning("初始化 provider %s 失败: %s", name, safe_msg)

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
            # v9.0: 熔断器检查
            if self._stats[name].is_circuit_open() and name != chain[-1]:
                logger.debug("熔断器断开，跳过 provider: %s", name)
                continue
            provider = self._providers[name]
            t0 = time.monotonic()
            try:
                result = provider.chat(messages, tools=tools, temperature=temperature, **kwargs)
                latency = time.monotonic() - t0
                self._stats[name].record_success(latency)
                if name != chain[0]:
                    logger.info(f"已 fallback 到 provider: {name}")
                return result
            except Exception as e:
                latency = time.monotonic() - t0
                self._stats[name].record_failure(latency)
                last_error = e
                # v9.0: 清洗错误消息中的敏感信息
                safe_msg = _scrub_sensitive(str(e))
                logger.warning("Provider %s 调用失败: %s，尝试 fallback...", name, safe_msg)

        raise RuntimeError(f"所有 provider 均失败，最后错误: {type(last_error).__name__}")

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
            # v9.0: 熔断器检查
            if self._stats[name].is_circuit_open() and name != chain[-1]:
                logger.debug("熔断器断开，跳过 stream provider: %s", name)
                continue
            provider = self._providers[name]
            t0 = time.monotonic()
            try:
                result = provider.stream_chat(messages, tools=tools, temperature=temperature, **kwargs)
                latency = time.monotonic() - t0
                self._stats[name].record_success(latency)
                return result
            except Exception as e:
                latency = time.monotonic() - t0
                self._stats[name].record_failure(latency)
                last_error = e
                safe_msg = _scrub_sensitive(str(e))
                logger.warning("Provider %s stream 失败: %s，尝试 fallback...", name, safe_msg)

        raise RuntimeError(f"所有 provider stream 均失败，最后错误: {type(last_error).__name__}")

    def get_context_length(self, provider_name: str | None = None) -> int:
        """获取指定 provider 的上下文窗口大小"""
        provider = self.get_provider(provider_name)
        return provider.context_length

    def list_providers(self) -> list[dict]:
        """列出所有已注册 provider 的信息（含性能统计）"""
        result = []
        for name, provider in self._providers.items():
            info = provider.get_info()
            info["stats"] = self._stats[name].to_dict()
            result.append(info)
        return result

    def get_provider_stats(self) -> dict:
        """获取所有 provider 的性能统计摘要"""
        return {name: stats.to_dict() for name, stats in self._stats.items()}
