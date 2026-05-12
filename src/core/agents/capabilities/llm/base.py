"""
LLM Provider 抽象接口

定义统一的 LLM 调用接口，支持多种 LLM 实现
"""

import asyncio
import json as _json
import aiohttp
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator
from enum import Enum

from ...exceptions import LLMTimeoutError, LLMResponseError, LLMRateLimitError, LLMProviderError


class FinishReason(str, Enum):
    """完成原因"""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


@dataclass
class LLMMessage:
    """统一的消息格式"""

    role: str  # system, user, assistant, tool
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class LLMResponse:
    """统一的响应格式"""

    content: str
    tool_calls: Optional[List[Dict]] = None
    finish_reason: FinishReason = FinishReason.STOP
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict] = None


@dataclass
class LLMConfig:
    """LLM 配置"""

    api_key: str
    model: str
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: float = 60.0


class LLMProvider(ABC):
    """LLM Provider 抽象接口"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建持久化 ClientSession（复用连接池）"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._session

    async def close(self):
        """关闭内部 session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _safe_json_response(self, coro) -> Dict[str, Any]:
        """包装 HTTP 请求，将超时和格式错误转为框架异常"""
        try:
            async with coro as resp:
                text = await resp.text()
                if resp.status != 200:
                    if resp.status == 429:
                        raise LLMRateLimitError(self.name)
                    raise LLMProviderError(self.name, text, resp.status)
                try:
                    return _json.loads(text)
                except _json.JSONDecodeError as e:
                    raise LLMResponseError(f"{self.name} returned invalid JSON: {e}")
        except asyncio.TimeoutError:
            raise LLMTimeoutError(f"{self.name} request timed out after {self.config.timeout}s")

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            tools: 工具定义列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            LLM 响应
        """
        pass

    @abstractmethod
    async def stream_chat(
        self, messages: List[LLMMessage], tools: Optional[List[Dict]] = None, **kwargs
    ) -> AsyncIterator[str]:
        """
        流式聊天

        Args:
            messages: 消息列表
            tools: 工具定义列表
            **kwargs: 其他参数

        Yields:
            响应文本片段
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """是否支持工具调用"""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """是否支持流式响应"""
        pass


__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "FinishReason",
]
