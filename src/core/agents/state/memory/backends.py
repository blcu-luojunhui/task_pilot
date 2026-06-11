"""可插拔记忆检索后端 — 关键词 / 语义向量"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from .long_term import MemoryEntry


class MemoryRetriever(Protocol):
    """记忆检索后端协议"""

    async def index(self, entries: List[MemoryEntry]) -> None: ...
    async def search(self, query: str, k: int) -> List[MemoryEntry]: ...


@dataclass
class KeywordRetriever:
    """关键词打分检索 — 等价现有行为，零依赖"""

    entries: List[MemoryEntry] = field(default_factory=list)

    async def index(self, entries: List[MemoryEntry]) -> None:
        self.entries = list(entries)

    async def search(self, query: str, k: int) -> List[MemoryEntry]:
        if not self.entries:
            return []
        query_lower = query.lower()
        scored: List[tuple] = []
        for e in self.entries:
            searchable = f"{e.key} {e.category} {str(e.value)}".lower()
            score = sum(1 for word in query_lower.split() if word in searchable)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:k]]


@dataclass
class EmbeddingRetriever:
    """语义向量检索 — 兼容任何 embedding provider"""

    embed_fn: Callable[[str], Any]
    entries: List[MemoryEntry] = field(default_factory=list)
    vectors: List[List[float]] = field(default_factory=list)
    importance_weight: float = 0.3
    decay_weight: float = 0.1
    decay_half_life_hours: float = 24.0

    async def index(self, entries: List[MemoryEntry]) -> None:
        self.entries = list(entries)
        self.vectors = []
        for e in self.entries:
            searchable = f"{e.key}: {str(e.value)[:1000]}"
            try:
                vec = await self._embed(searchable)
                self.vectors.append(vec)
            except Exception:
                self.vectors.append([0.0])

    async def search(self, query: str, k: int) -> List[MemoryEntry]:
        if not self.entries:
            return []
        try:
            query_vec = await self._embed(query)
        except Exception:
            # fallback to keyword if embedding fails
            kw = KeywordRetriever(self.entries)
            return await kw.search(query, k)

        scored = []
        now = time.time()
        for i, (entry, vec) in enumerate(zip(self.entries, self.vectors)):
            relevance = self._cosine_similarity(query_vec, vec)
            importance_score = entry.importance * self.importance_weight
            age_hours = (now - entry.created_at.timestamp()) / 3600
            decay = math.exp(-self.decay_weight * age_hours / self.decay_half_life_hours)
            total = relevance + importance_score + decay * 0.1
            scored.append((total, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:k]]

    async def _embed(self, text: str) -> List[float]:
        result = self.embed_fn(text)
        import inspect
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            return result
        if hasattr(result, "data"):
            return list(result.data[0].embedding)
        return list(result)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
