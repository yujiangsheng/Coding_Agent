"""LLM Provider 抽象与具体实现

定义统一的 LLMProvider 接口，以及 Ollama / OpenAI / Anthropic / DeepSeek
四种具体实现。所有 provider 暴露相同的 ``chat()`` 和 ``stream_chat()`` 方法，
返回统一的消息格式 ``{"role": "assistant", "content": "...", "tool_calls": [...]}``。

v3.1: 新增 Vision/图片输入支持（对标 Claude Code / Cursor 的多模态能力）
"""

from __future__ import annotations

import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ────────────────────────── Vision 辅助 ──────────────────────────

def encode_image(image_path: str) -> tuple[str, str]:
    """将本地图片编码为 base64 字符串并检测 MIME 类型

    Returns:
        (base64_data, media_type) — e.g. ("iVBOR...", "image/png")
    """
    ext_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    ext = os.path.splitext(image_path)[1].lower()
    media_type = ext_map.get(ext, "image/png")

    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, media_type


# ────────────────────────── 统一响应格式 ──────────────────────────

def _normalize_tool_calls(raw_calls: list | None) -> list[dict] | None:
    """将各 provider 的 tool_calls 格式标准化为 Ollama 风格。"""
    if not raw_calls:
        return None
    normalized = []
    for tc in raw_calls:
        if isinstance(tc, dict):
            func = tc.get("function", tc)
            name = func.get("name", "")
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            normalized.append({"function": {"name": name, "arguments": args}})
        else:
            # Anthropic tool_use block
            if hasattr(tc, "name"):
                normalized.append({
                    "function": {
                        "name": tc.name,
                        "arguments": tc.input if hasattr(tc, "input") else {},
                    }
                })
    return normalized if normalized else None


# ────────────────────────── 基类 ──────────────────────────

class LLMProvider(ABC):
    """LLM Provider 统一接口"""

    def __init__(self, model: str, temperature: float = 0.3, **kwargs):
        self.model = model
        self.temperature = temperature
        self.context_length: int = kwargs.get("context_length", 32768)

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> dict:
        """同步聊天，返回 ``{"role": "assistant", "content": ..., "tool_calls": ...}``"""
        ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        **kwargs,
    ) -> dict:
        """流式聊天，返回组装后的完整消息（与 chat 返回格式一致）。"""
        ...

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__

    def get_info(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "context_length": self.context_length,
        }


# ────────────────────────── Ollama ──────────────────────────

class OllamaProvider(LLMProvider):
    """本地 Ollama 模型 provider"""

    def __init__(self, model: str = "qwen3-coder:30b", temperature: float = 0.3, **kwargs):
        super().__init__(model, temperature, **kwargs)
        self._host = kwargs.get("host", "http://127.0.0.1:11434")

    @staticmethod
    def _prepare_ollama_messages(messages: list[dict]) -> list[dict]:
        """为 Ollama 消息添加 images 支持（base64 列表）"""
        prepared = []
        for m in messages:
            entry = dict(m)
            images = entry.pop("images", None)
            if images and entry.get("role") == "user":
                img_data = []
                for img in images:
                    if os.path.isfile(img):
                        data, _ = encode_image(img)
                        img_data.append(data)
                    elif img.startswith(("http://", "https://")):
                        # Ollama 不直接支持 URL，跳过
                        pass
                    else:
                        # 假定已是 base64 字符串
                        img_data.append(img)
                if img_data:
                    entry["images"] = img_data
            prepared.append(entry)
        return prepared

    def chat(self, messages, tools=None, temperature=None, **kwargs):
        import ollama
        temp = temperature if temperature is not None else self.temperature
        prepared = self._prepare_ollama_messages(messages)
        resp = ollama.chat(
            model=self.model,
            messages=prepared,
            tools=tools or None,
            options={"temperature": temp},
        )
        msg = resp.get("message", {})
        return {
            "role": "assistant",
            "content": msg.get("content", ""),
            "tool_calls": _normalize_tool_calls(msg.get("tool_calls")),
        }

    def stream_chat(self, messages, tools=None, temperature=None, **kwargs):
        import ollama
        temp = temperature if temperature is not None else self.temperature
        prepared = self._prepare_ollama_messages(messages)
        stream = ollama.chat(
            model=self.model,
            messages=prepared,
            tools=tools or None,
            options={"temperature": temp},
            stream=True,
        )
        assembled = {"role": "assistant", "content": ""}
        tool_calls = []
        for chunk in stream:
            msg = chunk.get("message", {})
            if msg.get("content"):
                assembled["content"] += msg["content"]
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
        assembled["tool_calls"] = _normalize_tool_calls(tool_calls)
        return assembled


# ────────────────────────── OpenAI ──────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI API provider（GPT-4o / GPT-4.5 / o3 等）"""

    def __init__(self, model: str = "gpt-4o", temperature: float = 0.3, **kwargs):
        super().__init__(model, temperature, **kwargs)
        self._api_key = kwargs.get("api_key", "")
        self._base_url = kwargs.get("base_url", None)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            client_kwargs = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            self._client = OpenAI(**client_kwargs)
        return self._client

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """Ollama tool schema → OpenAI tool schema"""
        if not tools:
            return None
        openai_tools = []
        for t in tools:
            func = t.get("function", t)
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                },
            })
        return openai_tools

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """统一消息格式到 OpenAI 格式（支持 Vision 多模态）"""
        converted = []
        for m in messages:
            role = m.get("role", "user")
            if role == "tool":
                converted.append({
                    "role": "tool",
                    "content": m.get("content", ""),
                    "tool_call_id": m.get("tool_call_id", "call_placeholder"),
                })
            else:
                entry = {"role": role}
                # Vision: 如果消息包含 images 字段，使用多模态格式
                images = m.get("images", [])
                text = m.get("content", "")
                if images and role == "user":
                    content_parts = []
                    if text:
                        content_parts.append({"type": "text", "text": text})
                    for img in images:
                        if img.startswith(("http://", "https://")):
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": img},
                            })
                        elif os.path.isfile(img):
                            data, media = encode_image(img)
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{media};base64,{data}"},
                            })
                    entry["content"] = content_parts
                else:
                    entry["content"] = text
                if m.get("tool_calls") and role == "assistant":
                    tc_list = []
                    for i, tc in enumerate(m["tool_calls"]):
                        func = tc.get("function", tc)
                        tc_list.append({
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": func.get("name", ""),
                                "arguments": json.dumps(
                                    func.get("arguments", {}), ensure_ascii=False
                                ),
                            },
                        })
                    entry["tool_calls"] = tc_list
                    if not entry["content"]:
                        entry["content"] = None
                converted.append(entry)
        return converted

    def chat(self, messages, tools=None, temperature=None, **kwargs):
        client = self._get_client()
        temp = temperature if temperature is not None else self.temperature
        call_kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temp,
        }
        openai_tools = self._convert_tools(tools)
        if openai_tools:
            call_kwargs["tools"] = openai_tools
        resp = client.chat.completions.create(**call_kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tool_calls.append({"function": {"name": tc.function.name, "arguments": args}})
        return {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls,
        }

    def stream_chat(self, messages, tools=None, temperature=None, **kwargs):
        client = self._get_client()
        temp = temperature if temperature is not None else self.temperature
        call_kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temp,
            "stream": True,
        }
        openai_tools = self._convert_tools(tools)
        if openai_tools:
            call_kwargs["tools"] = openai_tools
        stream = client.chat.completions.create(**call_kwargs)
        assembled = {"role": "assistant", "content": ""}
        tool_calls_acc: dict[int, dict] = {}
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue
            if delta.content:
                assembled["content"] += delta.content
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"name": "", "arguments": ""}
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_acc[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments
        if tool_calls_acc:
            tcs = []
            for _idx in sorted(tool_calls_acc):
                tc = tool_calls_acc[_idx]
                args = tc["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tcs.append({"function": {"name": tc["name"], "arguments": args}})
            assembled["tool_calls"] = tcs
        else:
            assembled["tool_calls"] = None
        return assembled


# ────────────────────────── Anthropic ──────────────────────────

class AnthropicProvider(LLMProvider):
    """Anthropic API provider（Claude Opus 4 / Sonnet 4 等）"""

    def __init__(self, model: str = "claude-sonnet-4-20250514", temperature: float = 0.3, **kwargs):
        super().__init__(model, temperature, **kwargs)
        self._api_key = kwargs.get("api_key", "")
        self._client = None
        self._max_tokens = kwargs.get("max_tokens", 8192)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """Ollama tool schema → Anthropic tool schema"""
        if not tools:
            return None
        anthropic_tools = []
        for t in tools:
            func = t.get("function", t)
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return anthropic_tools

    def _extract_system(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """提取 system 消息（Anthropic 需要单独传 system 参数），支持 Vision"""
        system_parts = []
        non_system = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(m.get("content", ""))
            elif m.get("role") == "tool":
                non_system.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "placeholder", "content": m.get("content", "")}],
                })
            else:
                entry = {"role": m.get("role", "user")}
                # Vision: 如果消息包含 images 字段
                images = m.get("images", [])
                if images and m.get("role") == "user":
                    content_blocks = []
                    text = m.get("content", "")
                    if text:
                        content_blocks.append({"type": "text", "text": text})
                    for img in images:
                        if img.startswith(("http://", "https://")):
                            content_blocks.append({
                                "type": "image",
                                "source": {"type": "url", "url": img},
                            })
                        elif os.path.isfile(img):
                            data, media = encode_image(img)
                            content_blocks.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media, "data": data},
                            })
                    entry["content"] = content_blocks
                elif m.get("tool_calls") and m.get("role") == "assistant":
                    content_blocks = []
                    if m.get("content"):
                        content_blocks.append({"type": "text", "text": m["content"]})
                    for tc in m["tool_calls"]:
                        func = tc.get("function", tc)
                        content_blocks.append({
                            "type": "tool_use",
                            "id": "placeholder",
                            "name": func.get("name", ""),
                            "input": func.get("arguments", {}),
                        })
                    entry["content"] = content_blocks
                else:
                    entry["content"] = m.get("content", "")
                non_system.append(entry)

        # Anthropic: messages must alternate user/assistant
        merged = self._merge_consecutive_roles(non_system)
        return "\n\n".join(system_parts), merged

    def _merge_consecutive_roles(self, messages: list[dict]) -> list[dict]:
        """合并连续相同 role 的消息（Anthropic 要求严格交替）"""
        if not messages:
            return []
        merged = [messages[0]]
        for m in messages[1:]:
            if m["role"] == merged[-1]["role"]:
                prev_content = merged[-1].get("content", "")
                curr_content = m.get("content", "")
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + "\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    merged[-1]["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    merged[-1]["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + [{"type": "text", "text": curr_content}]
            else:
                merged.append(m)
        return merged

    def _apply_prompt_caching(self, system: str) -> list[dict] | str:
        """将 system prompt 转换为带缓存控制的格式（v3.2 — Prompt Caching）

        Anthropic prompt caching 可将 system prompt 缓存起来，
        后续请求中标记 cache_control.ephemeral 即可复用缓存，
        降低 ~90% 的 system prompt 处理成本。
        """
        if not system or len(system) < 500:
            return system  # 太短不值得缓存
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def chat(self, messages, tools=None, temperature=None, **kwargs):
        client = self._get_client()
        temp = temperature if temperature is not None else self.temperature
        system, msgs = self._extract_system(messages)
        call_kwargs = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": temp,
        }
        if system:
            call_kwargs["system"] = self._apply_prompt_caching(system)
        anthropic_tools = self._convert_tools(tools)
        if anthropic_tools:
            call_kwargs["tools"] = anthropic_tools
        resp = client.messages.create(**call_kwargs)
        content_text = ""
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "function": {"name": block.name, "arguments": block.input}
                })
        return {
            "role": "assistant",
            "content": content_text,
            "tool_calls": tool_calls if tool_calls else None,
        }

    def stream_chat(self, messages, tools=None, temperature=None, **kwargs):
        client = self._get_client()
        temp = temperature if temperature is not None else self.temperature
        system, msgs = self._extract_system(messages)
        call_kwargs = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": temp,
        }
        if system:
            call_kwargs["system"] = self._apply_prompt_caching(system)
        anthropic_tools = self._convert_tools(tools)
        if anthropic_tools:
            call_kwargs["tools"] = anthropic_tools
        assembled = {"role": "assistant", "content": ""}
        tool_calls = []
        current_tool: dict | None = None
        with client.messages.stream(**call_kwargs) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_start":
                        block = event.content_block
                        if hasattr(block, "type") and block.type == "tool_use":
                            current_tool = {"name": block.name, "arguments": ""}
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "text"):
                            assembled["content"] += delta.text
                        elif hasattr(delta, "partial_json"):
                            if current_tool is not None:
                                current_tool["arguments"] += delta.partial_json
                    elif event.type == "content_block_stop":
                        if current_tool is not None:
                            args = current_tool["arguments"]
                            try:
                                args = json.loads(args) if args else {}
                            except json.JSONDecodeError:
                                args = {"raw": args}
                            tool_calls.append({
                                "function": {"name": current_tool["name"], "arguments": args}
                            })
                            current_tool = None
        assembled["tool_calls"] = tool_calls if tool_calls else None
        return assembled


# ────────────────────────── DeepSeek ──────────────────────────

class DeepSeekProvider(OpenAIProvider):
    """DeepSeek API provider（兼容 OpenAI 格式）"""

    def __init__(self, model: str = "deepseek-chat", temperature: float = 0.3, **kwargs):
        kwargs.setdefault("base_url", "https://api.deepseek.com")
        super().__init__(model, temperature, **kwargs)


# ────────────────────────── 工厂函数 ──────────────────────────

_PROVIDER_MAP = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "deepseek": DeepSeekProvider,
}


def create_provider(provider_type: str, **kwargs) -> LLMProvider:
    """根据 provider 类型创建 LLM provider 实例。

    Args:
        provider_type: ollama / openai / anthropic / deepseek
        **kwargs: model, temperature, api_key, base_url 等

    Returns:
        LLMProvider 实例
    """
    cls = _PROVIDER_MAP.get(provider_type.lower())
    if cls is None:
        available = ", ".join(_PROVIDER_MAP.keys())
        raise ValueError(f"未知 provider: {provider_type}，可选: {available}")
    return cls(**kwargs)
