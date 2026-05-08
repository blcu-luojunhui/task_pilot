"""
TokenCounter — 基于 tiktoken 的精确 token 计数

自动根据模型名选择正确的编码器，无 tiktoken 时回退到字符估算。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 模型 → tiktoken 编码名称映射
_MODEL_ENCODING_MAP = {
    # OpenAI
    "gpt-4o": "o200k_base",
    "gpt-4.1": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    # DeepSeek (兼容 OpenAI tokenizer)
    "deepseek-chat": "cl100k_base",
    "deepseek-reasoner": "cl100k_base",
    # Claude — 无公开 tokenizer，使用 cl100k_base 作为近似
    "claude-sonnet-4-6": "cl100k_base",
    "claude-3-opus-20240229": "cl100k_base",
    "claude-3.5-sonnet": "cl100k_base",
    "claude-3.5-haiku": "cl100k_base",
}

# 中文字符 token 比率（用于字符回退估算）
FALLBACK_CHARS_PER_TOKEN = 4.0


class TokenCounter:
    """精确 token 计数器（优先使用 tiktoken）"""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self._encoding = None
        self._init_encoding(model)

    def _init_encoding(self, model: str):
        encoding_name = _MODEL_ENCODING_MAP.get(model)
        if encoding_name is None:
            encoding_name = "cl100k_base"

        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding(encoding_name)
            logger.debug("TokenCounter using tiktoken encoding '%s' for model '%s'", encoding_name, model)
        except Exception:
            logger.debug("tiktoken not available, falling back to char-based estimation for '%s'", model)
            self._encoding = None

    def count(self, text: str) -> int:
        """计算文本的精确 token 数"""
        if not text:
            return 0
        if self._encoding:
            return len(self._encoding.encode(text))
        # 回退：字符估算
        return max(1, int(len(text) / FALLBACK_CHARS_PER_TOKEN))

    def count_messages(self, messages: list) -> int:
        """计算消息列表的 token 数（含角色开销）"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count(content)
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                import json

                total += self.count(json.dumps(tool_calls, ensure_ascii=False))
            # 每条消息的协议开销
            total += 4
        return total

    @property
    def is_precise(self) -> bool:
        """是否使用精确 tokenizer"""
        return self._encoding is not None


__all__ = ["TokenCounter"]
