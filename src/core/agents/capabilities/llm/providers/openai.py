"""
OpenAI Provider 实现
"""

import aiohttp
from typing import List, Dict, Optional, AsyncIterator
from ..base import LLMProvider, LLMMessage, LLMResponse, LLMConfig, FinishReason
from ....exceptions import LLMProviderError, LLMRateLimitError


class OpenAIProvider(LLMProvider):
    """OpenAI Provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = "https://api.openai.com/v1"

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
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": [self._convert_message(m) for m in messages],
            "temperature": temperature or self.config.temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if max_tokens or self.config.max_tokens:
            payload["max_tokens"] = max_tokens or self.config.max_tokens

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    if resp.status == 429:
                        raise LLMRateLimitError("openai")
                    raise LLMProviderError("openai", error_text, resp.status)

                data = await resp.json()

                choice = data["choices"][0]
                message = choice["message"]

                return LLMResponse(
                    content=message.get("content") or "",
                    tool_calls=message.get("tool_calls"),
                    finish_reason=FinishReason(choice.get("finish_reason", "stop")),
                    usage=data.get("usage"),
                    raw_response=data,
                )

    async def stream_chat(
        self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None, **kwargs
    ) -> AsyncIterator[str]:
        """流式聊天"""
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": [self._convert_message(m) for m in messages],
            "temperature": self.config.temperature,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            import json

                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except:
                            continue

    def _convert_message(self, message: LLMMessage) -> Dict:
        """转换消息格式"""
        result = {"role": message.role, "content": message.content}
        if message.name:
            result["name"] = message.name
        if message.tool_calls:
            result["tool_calls"] = message.tool_calls
        if message.tool_call_id:
            result["tool_call_id"] = message.tool_call_id
        return result

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True


__all__ = ["OpenAIProvider"]
