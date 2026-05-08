"""
Claude Provider 实现
"""

import json
import aiohttp
from typing import List, Dict, Optional, AsyncIterator
from ..base import LLMProvider, LLMMessage, LLMResponse, LLMConfig, FinishReason
from ....exceptions import LLMProviderError, LLMRateLimitError


class ClaudeProvider(LLMProvider):
    """Claude (Anthropic) Provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = "https://api.anthropic.com/v1"

    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """发送聊天请求"""
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # Claude 需要分离 system 消息
        system_message = None
        user_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                user_messages.append(self._convert_message(msg))

        payload = {
            "model": self.config.model,
            "messages": user_messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else (self.config.max_tokens or 4096),
        }

        if system_message:
            payload["system"] = system_message

        if tools:
            payload["tools"] = self._convert_tools(tools)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    if resp.status == 429:
                        raise LLMRateLimitError("claude")
                    raise LLMProviderError("claude", error_text, resp.status)

                data = await resp.json()

                content = data.get("content", [])
                text_content = ""
                tool_calls = []

                for block in content:
                    if block["type"] == "text":
                        text_content += block["text"]
                    elif block["type"] == "tool_use":
                        tool_calls.append(
                            {
                                "id": block["id"],
                                "type": "function",
                                "function": {"name": block["name"], "arguments": block["input"]},
                            }
                        )

                stop_reason = data.get("stop_reason", "stop")
                # Claude 的 stop_reason 值映射到内部统一枚举
                _CLAUDE_REASON_MAP = {
                    "end_turn": FinishReason.STOP,
                    "max_tokens": FinishReason.LENGTH,
                    "tool_use": FinishReason.TOOL_CALLS,
                    "stop_sequence": FinishReason.STOP,
                }
                finish_reason = _CLAUDE_REASON_MAP.get(stop_reason)
                if finish_reason is None:
                    finish_reason = FinishReason.STOP

                return LLMResponse(
                    content=text_content,
                    tool_calls=tool_calls if tool_calls else None,
                    finish_reason=finish_reason,
                    usage=data.get("usage"),
                    raw_response=data,
                )

    async def stream_chat(
        self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None, **kwargs
    ) -> AsyncIterator[str]:
        """流式聊天"""
        # Claude 流式实现
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        system_message = None
        user_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                user_messages.append(self._convert_message(msg))

        payload = {
            "model": self.config.model,
            "messages": user_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens or 4096,
            "stream": True,
        }

        if system_message:
            payload["system"] = system_message

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except (json.JSONDecodeError, KeyError):
                            continue

    def _convert_message(self, message: LLMMessage) -> Dict:
        """转换消息格式"""
        return {
            "role": message.role if message.role != "system" else "user",
            "content": message.content,
        }

    def _convert_tools(self, tools: List[Dict]) -> List[Dict]:
        """转换工具格式为 Claude 格式"""
        claude_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                claude_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )
        return claude_tools

    @property
    def name(self) -> str:
        return "claude"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True


__all__ = ["ClaudeProvider"]
