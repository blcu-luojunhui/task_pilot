"""
LLM Provider 抽象接口

定义统一的 LLM 调用接口，支持多种 LLM 实现
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator
from enum import Enum


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

    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
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
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        **kwargs
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
