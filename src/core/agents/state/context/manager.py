"""Context window manager implementation"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import logging

from .tokenizer import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class ContextWindowManager:
    """
    管理上下文窗口大小和消息历史

    策略：
    1. 保留 system 消息（不截断）
    2. 保留最近 N 条消息
    3. 中间消息按时间从旧到新截断

    使用 TokenCounter 进行精确 token 计数（优先 tiktoken，回退字符估算）。
    """

    max_tokens: int = 60000
    reserve_ratio: float = 0.1  # 为响应预留 10% 空间
    token_counter: TokenCounter = field(default_factory=TokenCounter)
    model: str = "gpt-4o"

    def __post_init__(self):
        if self.model != "gpt-4o" and isinstance(self.token_counter, TokenCounter):
            self.token_counter = TokenCounter(model=self.model)

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
        self, messages: List[Dict[str, Any]], max_tokens: Optional[int] = None
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
        计算文本的精确 token 数

        Args:
            text: 文本内容

        Returns:
            token 数
        """
        return self.token_counter.count(text)

    def _estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表的总 token 数"""
        return self.token_counter.count_messages(messages)

    def _truncate_middle(
        self, messages: List[Dict[str, Any]], max_tokens: int
    ) -> List[Dict[str, Any]]:
        """
        从中间截断消息

        保留策略：
        - 第一条 system 消息（如果有）
        - 最近的消息（从后往前保留）
        - tool-call 对（assistant(tool_calls) + tool(tool_call_id)）整组保留或丢弃
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
            return system_msgs

        # 为 tool 消息建立反向索引：tool_call_id → 消息位置
        tool_msg_by_call_id: Dict[str, int] = {}
        for i, msg in enumerate(other_msgs):
            if msg.get("role") == "tool" and msg.get("tool_call_id"):
                tool_msg_by_call_id[msg["tool_call_id"]] = i

        # 从后往前保留消息，以 tool-call 对为原子单位
        kept_indices: set = set()
        used_tokens = 0
        i = len(other_msgs) - 1

        while i >= 0 and used_tokens < remaining_budget:
            msg = other_msgs[i]
            if i in kept_indices:
                i -= 1
                continue

            # assistant 消息携带 tool_calls 时，需连带保留对应的 tool 结果
            tool_call_ids: List[str] = []
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id")
                    if tc_id:
                        tool_call_ids.append(tc_id)

            # 计算整组 token
            group_indices = {i}
            for tc_id in tool_call_ids:
                tool_idx = tool_msg_by_call_id.get(tc_id)
                if tool_idx is not None:
                    group_indices.add(tool_idx)

            # 估算整组 token（含 tool 结果）
            group_msgs = [other_msgs[idx] for idx in sorted(group_indices)]
            group_tokens = self._estimate_messages_tokens(group_msgs)
            if used_tokens + group_tokens > remaining_budget:
                break

            kept_indices.update(group_indices)
            used_tokens += group_tokens
            i = min(group_indices) - 1 if group_indices else i - 1

        # 清理孤儿 tool 消息（其配对的 assistant(tool_calls) 已被丢弃）
        for idx in list(kept_indices):
            msg = other_msgs[idx]
            if msg.get("role") == "tool":
                tc_id = msg.get("tool_call_id")
                if tc_id:
                    # 查找配对的 assistant
                    has_pair = any(
                        j in kept_indices
                        and other_msgs[j].get("role") == "assistant"
                        and any(tc.get("id") == tc_id for tc in (other_msgs[j].get("tool_calls") or []))
                        for j in kept_indices
                        if j != idx
                    )
                    if not has_pair:
                        kept_indices.discard(idx)

        kept_msgs = [other_msgs[idx] for idx in sorted(kept_indices)]
        result = system_msgs + kept_msgs

        if len(result) < len(messages):
            dropped = len(messages) - len(result)
            logger.info(f"Context compacted: dropped {dropped} messages, kept {len(result)}")

        return result
