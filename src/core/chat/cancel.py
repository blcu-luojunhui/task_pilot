"""ChatCancelRegistry：轻量 in-memory 取消信号注册表。

普通 chat（未升级到 agentic）不经过 task_manager，取消信号走这个注册表。
一旦 LLM 调用 escalate_to_agent 升级，取消机制切换到 task_manager DB 轮询。
"""
from __future__ import annotations

import asyncio
from typing import Dict


class ChatCancelRegistry:
    """线程安全的 trace_id → asyncio.Event 映射。"""

    _events: Dict[str, asyncio.Event] = {}

    @classmethod
    def register(cls, trace_id: str) -> None:
        cls._events[trace_id] = asyncio.Event()

    @classmethod
    def cancel(cls, trace_id: str) -> bool:
        """设置取消信号。返回 True 表示存在该 trace_id 并已设置。"""
        evt = cls._events.get(trace_id)
        if evt is None:
            return False
        evt.set()
        return True

    @classmethod
    def is_cancelled(cls, trace_id: str) -> bool:
        evt = cls._events.get(trace_id)
        if evt is None:
            return False
        return evt.is_set()

    @classmethod
    def deregister(cls, trace_id: str) -> None:
        cls._events.pop(trace_id, None)


__all__ = ["ChatCancelRegistry"]
