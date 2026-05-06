"""
长期记忆 - 存储跨会话的知识和经验
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path


@dataclass
class MemoryEntry:
    """记忆条目"""
    key: str
    value: Any
    category: str = "general"
    importance: float = 0.5  # 0-1
    created_at: datetime = field(default_factory=datetime.now)
    accessed_count: int = 0
    last_accessed: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LongTermMemory:
    """长期记忆存储"""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path
        self.memories: Dict[str, MemoryEntry] = {}

        if storage_path and storage_path.exists():
            self.load()

    def store(self, key: str, value: Any, category: str = "general",
              importance: float = 0.5, **metadata):
        """存储记忆"""
        entry = MemoryEntry(
            key=key,
            value=value,
            category=category,
            importance=importance,
            metadata=metadata
        )
        self.memories[key] = entry
