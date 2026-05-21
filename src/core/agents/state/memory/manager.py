"""
MemoryManager — 记忆读写入口，串联短期/长期记忆，供 Think/Observe 调用
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .short_term import ShortTermMemory
from .long_term import LongTermMemory


@dataclass
class MemoryManager:
    """统一记忆管理器，在 Think/Observe 中读写记忆"""

    short_term: ShortTermMemory = field(default_factory=ShortTermMemory)
    long_term: Optional[LongTermMemory] = None
    max_short_term_items: int = 50

    def retrieve(self, query: str, k: int = 3) -> List[str]:
        """从短期记忆中检索与 query 相关的记忆"""
        candidates = self.short_term.recent_tool_results
        if not candidates:
            return []

        query_lower = query.lower()
        scored: List[tuple] = []
        for item in candidates:
            text = f"{item.get('tool', '')} {str(item.get('result', ''))}"
            score = sum(1 for word in query_lower.split() if word in text.lower())
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            f"[{item['tool']}] {str(item['result'])[:500]}"
            for _, item in scored[:k]
        ]

    def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """添加记忆到短期存储"""
        self.short_term.add_tool_result(
            tool_name=metadata.get("tool", "unknown") if metadata else "unknown",
            result=content,
            **(metadata or {}),
        )
        if len(self.short_term.recent_tool_results) > self.max_short_term_items:
            self.short_term.recent_tool_results = self.short_term.recent_tool_results[
                -self.max_short_term_items:
            ]

    def clear(self) -> None:
        self.short_term.clear()

    async def persist_to_long_term(
        self, key: str, value: Any, category: str = "general", importance: float = 0.5
    ) -> None:
        if self.long_term is not None:
            await self.long_term.store(key=key, value=value, category=category, importance=importance)


__all__ = ["MemoryManager"]
