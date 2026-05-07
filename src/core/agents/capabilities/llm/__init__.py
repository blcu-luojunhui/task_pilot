"""
LLM Layer - LLM 集成

提供：
- base: LLM Provider 抽象接口
- providers: 各种 LLM 实现（OpenAI, Claude, DeepSeek）
- deepseek: 原有 DeepSeekPlanner（兼容层）
"""

from .base import LLMProvider, LLMMessage, LLMResponse, LLMConfig, FinishReason
from .providers import OpenAIProvider, ClaudeProvider, DeepSeekProvider
from .deepseek import DeepSeekPlanner, DeepSeekSettings, load_dotenv

__all__ = [
    # Base
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMConfig",
    "FinishReason",
    # Providers
    "OpenAIProvider",
    "ClaudeProvider",
    "DeepSeekProvider",
    # Legacy (兼容)
    "DeepSeekPlanner",
    "DeepSeekSettings",
    "load_dotenv",
]
