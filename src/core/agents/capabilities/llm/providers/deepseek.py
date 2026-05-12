"""
DeepSeek Provider 实现（重构现有实现）
"""

import json
from typing import List, Dict, Optional, AsyncIterator
from ..base import LLMProvider, LLMMessage, LLMResponse, LLMConfig, FinishReason


class DeepSeekProvider(LLMProvider):
    """DeepSeek Provider"""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = "https://api.deepseek.com"

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
            "temperature": temperature if temperature is not None else self.config.temperature,
        }

        if tools:
            payload["tools"] = tools

        resolved_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens
        if resolved_max_tokens:
            payload["max_tokens"] = resolved_max_tokens

        session = self._get_session()
        data = await self._safe_json_response(
            session.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        )

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

        session = self._get_session()
        async with session.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    def _convert_message(self, message: LLMMessage) -> Dict:
        """转换消息格式"""
        result = {"role": message.role, "content": message.content}
        if message.tool_calls:
            result["tool_calls"] = message.tool_calls
        if message.tool_call_id:
            result["tool_call_id"] = message.tool_call_id
        return result

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def supports_streaming(self) -> bool:
        return True


__all__ = ["DeepSeekProvider"]
