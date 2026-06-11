"""ArtifactStore — 超长工具结果落盘，对话保留引用 + 按需回读"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ArtifactRef:
    id: str
    path: Path
    total_lines: int
    total_chars: int
    preview: str  # 前 N 字符摘要


class ArtifactStore:
    """上下文卸载存储。超阈值工具结果写入文件，返回引用指针。"""

    def __init__(self, base_dir: Path | str, threshold_chars: int = 4000):
        self.base_dir = Path(base_dir)
        self.threshold_chars = threshold_chars
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def should_offload(self, content: str) -> bool:
        return len(content) > self.threshold_chars

    async def put(
        self, trace_id: str, tool_name: str, step: int, content: str
    ) -> ArtifactRef:
        artifact_id = f"{tool_name}_{step}_{uuid.uuid4().hex[:8]}"
        artifact_dir = self.base_dir / trace_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{artifact_id}.txt"

        lines = content.split("\n")
        total_chars = len(content)

        def _write():
            artifact_path.write_text(content, encoding="utf-8")

        await asyncio.to_thread(_write)
        logger.debug("Artifact saved: %s (%d chars)", artifact_id, total_chars)
        return ArtifactRef(
            id=artifact_id,
            path=artifact_path,
            total_lines=len(lines),
            total_chars=total_chars,
            preview=content[:200],
        )

    async def get(self, artifact_id: str, trace_id: str, offset: int = 0, limit: int = 2000) -> str:
        artifact_path = self.base_dir / trace_id / f"{artifact_id}.txt"
        if not artifact_path.exists():
            return f"Error: artifact {artifact_id} not found"

        def _read():
            with open(artifact_path, "r", encoding="utf-8") as f:
                if offset > 0:
                    f.seek(offset)
                return f.read(limit)

        return await asyncio.to_thread(_read)


__all__ = ["ArtifactStore", "ArtifactRef"]
