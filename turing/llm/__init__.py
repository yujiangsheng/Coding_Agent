"""LLM 多 Provider 抽象层

支持多种 LLM 后端统一调度，拉近与顶级 AI coding 工具的核心差距：

- **Ollama** — 本地模型（Qwen3-Coder / DeepSeek-Coder / CodeLlama 等）
- **OpenAI** — GPT-4o / GPT-4.5 / o3 等
- **Anthropic** — Claude Opus 4 / Sonnet 4 等
- **DeepSeek** — DeepSeek-V3 / DeepSeek-Coder 等
- **自定义 OpenAI 兼容** — 任何兼容 OpenAI API 的服务

通过 ModelRouter 实现智能路由：根据任务复杂度、token 预算、
模型长项自动选择最优 provider，支持 fallback 链。

Usage::

    from turing.llm import create_provider, ModelRouter

    # 直接使用单 provider
    provider = create_provider("openai", model="gpt-4o", api_key="sk-...")
    resp = provider.chat(messages, tools=tools)

    # 使用智能路由
    router = ModelRouter(config)
    resp = router.chat(messages, tools=tools, task_complexity=0.8)
"""

from turing.llm.provider import (
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
    AnthropicProvider,
    DeepSeekProvider,
    create_provider,
)
from turing.llm.router import ModelRouter

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "DeepSeekProvider",
    "create_provider",
    "ModelRouter",
]
