"""
MemoryManager — 记忆读写入口，串联短期/长期记忆，支持可插拔检索后端
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .short_term import ShortTermMemory
from .long_term import LongTermMemory, MemoryEntry
from .backends import KeywordRetriever, MemoryRetriever


@dataclass
class MemoryManager:
    """统一记忆管理器，在 Think/Observe 中读写记忆"""

    short_term: ShortTermMemory = field(default_factory=ShortTermMemory)
    long_term: Optional[LongTermMemory] = None
    retriever: Optional[MemoryRetriever] = None
    max_short_term_items: int = 50

    def retrieve(self, query: str, k: int = 3) -> List[str]:
        """从短期记忆中检索（关键词，保留向后兼容）"""
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

    async def aretrieve(self, query: str, k: int = 3) -> List[str]:
        """异步检索，支持语义后端。先从短期取，再查长期。"""
        results: List[str] = []

        # 1. 短期记忆 — 关键词
        results.extend(self.retrieve(query, k))

        # 2. 长期记忆 — 通过 retriever（如果配置了）
        if self.long_term and self.retriever:
            try:
                entries = list(self.long_term.memories.values())
                if entries:
                    await self.retriever.index(entries)
                    long_results = await self.retriever.search(query, k)
                    for e in long_results:
                        results.append(f"[{e.category}] {e.key}: {str(e.value)[:500]}")
            except Exception:
                pass

        return results[:k * 2]

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

    @staticmethod
    def build_memory_query(state: Any) -> str:
        """构建改进的检索 query：goal + 最近 observation 摘要"""
        goal = state.goal or ""
        recent = ""
        if hasattr(state, "steps") and state.steps:
            last_step = state.steps[-1]
            if last_step.observation and last_step.observation.result:
                obs_text = str(last_step.observation.result)[:200]
                recent = f" | recent: {obs_text}"
        return f"{goal}{recent}"


__all__ = ["MemoryManager"]
