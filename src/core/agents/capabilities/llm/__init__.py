"""
LLM Layer - LLM 集成

提供：
- base: LLM Provider 抽象接口
- providers: 各种 LLM 实现（OpenAI, Claude, DeepSeek）
- deepseek: 原有 DeepSeekPlanner（兼容层）
"""

from .base import LLMProvider, LLMMessage, LLMResponse, LLMConfig, FinishReason
from .providers import OpenAIProvider, ClaudeProvider, DeepSeekProvider


_LEGACY_EXPORTS = {"DeepSeekPlanner", "DeepSeekSettings", "load_dotenv"}


def __getattr__(name: str):
    """Load the deprecated planner only when legacy callers request it."""
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from . import deepseek as legacy

    return getattr(legacy, name)

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
    # Legacy (deprecated, remove in v5)
    "DeepSeekPlanner",
    "DeepSeekSettings",
    "load_dotenv",
]
