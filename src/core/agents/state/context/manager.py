"""Context window manager implementation"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


@dataclass
class ContextWindowManager:
    """
    管理上下文窗口大小和消息历史

    策略：
    1. 保留 system 消息（不截断）
    2. 保留最近 N 条消息
    3. 中间消息按时间从旧到新截断
    """

    max_tokens: int = 60000
    chars_per_token: float = 4.0  # 粗略估算
    reserve_ratio: float = 0.1   # 为响应预留 10% 空间

    def compact_if_needed(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        如果消息超过 token 限制，进行压缩

        策略：
        - 保留第一条 system 消息
        - 保留最近的消息
        - 从中间开始截断

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        total_tokens = self._estimate_messages_tokens(messages)
        effective_limit = int(self.max_tokens * (1 - self.reserve_ratio))

        if total_tokens <= effective_limit:
            return messages

        logger.info(
            f"Context compaction triggered: {total_tokens} tokens > {effective_limit} limit"
        )

        return self._truncate_middle(messages, effective_limit)

    def truncate_messages(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        截断消息以适应 token 限制

        Args:
            messages: 消息列表
            max_tokens: 最大 token 数（None 使用默认值）

        Returns:
            截断后的消息列表
        """
        limit = max_tokens or self.max_tokens
        return self._truncate_middle(messages, limit)

    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数

        Args:
            text: 文本内容

        Returns:
            估算的 token 数
        """
        return max(1, int(len(text) / self.chars_per_token))

    def _estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的总 token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            # tool_calls 也占 token
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                total += self.estimate_tokens(json.dumps(tool_calls, ensure_ascii=False))
            # 每条消息有固定开销（role, formatting）
            total += 4
        return total

    def _truncate_middle(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int
    ) -> List[Dict[str, Any]]:
        """
        从中间截断消息

        保留策略：
        - 第一条 system 消息（如果有）
        - 最近的消息（从后往前保留）
        """
        if not messages:
            return messages

        # 分离 system 消息和其他消息
        system_msgs = []
        other_msgs = []

        for msg in messages:
            if msg.get("role") == "system" and not system_msgs:
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        # 计算 system 消息占用的 token
        system_tokens = self._estimate_messages_tokens(system_msgs)
        remaining_budget = max_tokens - system_tokens

        if remaining_budget <= 0:
            # system 消息本身就超了，只保留 system
            return system_msgs

        # 从后往前保留消息
        kept_msgs = []
        used_tokens = 0

        for msg in reversed(other_msgs):
            msg_tokens = self._estimate_messages_tokens([msg])
            if used_tokens + msg_tokens > remaining_budget:
                break
            kept_msgs.insert(0, msg)
            used_tokens += msg_tokens

        result = system_msgs + kept_msgs

        if len(result) < len(messages):
            dropped = len(messages) - len(result)
            logger.info(f"Context compacted: dropped {dropped} messages, kept {len(result)}")

        return result
