"""
长期记忆 - 存储跨会话的知识和经验
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class MemoryEntry:
    """记忆条目"""

    key: str
    value: Any
    category: str = "general"
    importance: float = 0.5  # 0-1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_count: int = 0
    last_accessed: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LongTermMemory:
    """长期记忆存储（JSON file-backed）"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.memories: Dict[str, MemoryEntry] = {}

        if storage_path and storage_path.exists():
            self._load()

    def store(
        self, key: str, value: Any, category: str = "general", importance: float = 0.5, **metadata
    ):
        """存储记忆"""
        entry = MemoryEntry(
            key=key, value=value, category=category, importance=importance, metadata=metadata
        )
        self.memories[key] = entry
        if self.storage_path:
            self._save()

    def retrieve(self, key: str) -> Optional[MemoryEntry]:
        """按 key 精确检索"""
        entry = self.memories.get(key)
        if entry:
            entry.accessed_count += 1
            entry.last_accessed = datetime.now(timezone.utc)
        return entry

    def retrieve_by_category(
        self, category: str, min_importance: float = 0.0, limit: int = 20
    ) -> List[MemoryEntry]:
        """按类别检索，按重要性×时间衰减排序"""
        candidates = [
            e
            for e in self.memories.values()
            if e.category == category and e.importance >= min_importance
        ]
        candidates.sort(key=lambda e: e.importance, reverse=True)
        for entry in candidates[:limit]:
            entry.accessed_count += 1
            entry.last_accessed = datetime.now(timezone.utc)
        return candidates[:limit]

    def search(self, keyword: str, limit: int = 20) -> List[MemoryEntry]:
        """简单关键词搜索（匹配 key、value 字符串、category）"""
        keyword_lower = keyword.lower()
        results = []
        for entry in self.memories.values():
            searchable = f"{entry.key} {entry.category} {str(entry.value)}".lower()
            if keyword_lower in searchable:
                results.append(entry)
        results.sort(key=lambda e: e.importance, reverse=True)
        for entry in results[:limit]:
            entry.accessed_count += 1
            entry.last_accessed = datetime.now(timezone.utc)
        return results[:limit]

    def delete(self, key: str) -> bool:
        """删除记忆"""
        if key in self.memories:
            del self.memories[key]
            if self.storage_path:
                self._save()
            return True
        return False

    def clear(self):
        """清空所有记忆"""
        self.memories.clear()
        if self.storage_path:
            self._save()

    # ── 私有方法 ──────────────────────────────────────

    def _save(self):
        """持久化到 JSON 文件"""
        if not self.storage_path:
            return
        data = {
            "schema_version": 1,
            "memories": {
                key: {
                    "key": e.key,
                    "value": e.value,
                    "category": e.category,
                    "importance": e.importance,
                    "created_at": e.created_at.isoformat(),
                    "accessed_count": e.accessed_count,
                    "last_accessed": e.last_accessed.isoformat() if e.last_accessed else None,
                    "metadata": e.metadata,
                }
                for key, e in self.memories.items()
            },
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self):
        """从 JSON 文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return
        with open(self.storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, raw in data.get("memories", {}).items():
            entry = MemoryEntry(
                key=raw["key"],
                value=raw["value"],
                category=raw.get("category", "general"),
                importance=raw.get("importance", 0.5),
                created_at=datetime.fromisoformat(raw["created_at"])
                if raw.get("created_at")
                else datetime.now(timezone.utc),
                accessed_count=raw.get("accessed_count", 0),
                last_accessed=datetime.fromisoformat(raw["last_accessed"])
                if raw.get("last_accessed")
                else None,
                metadata=raw.get("metadata", {}),
            )
            self.memories[key] = entry


__all__ = ["LongTermMemory", "MemoryEntry"]
