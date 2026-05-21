"""
异步事件持久化器 — 消费 in-memory 队列，批量写入 agent_events 表。

设计要点:
- publish 调用链不阻塞（enqueue 即返回）
- 批量 INSERT IGNORE，达到 batch_size 或 flush_interval 时写出
- 队列满时 drop oldest（背压策略），不阻塞上游
- 优雅关闭时 flush 剩余事件
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.infra.database import AsyncMySQLPool

logger = logging.getLogger(__name__)

SQL_INSERT = (
    "INSERT IGNORE INTO agent_events "
    "(trace_id, sequence, event_type, source, step, payload) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)


@dataclass
class _EventRow:
    trace_id: str
    sequence: int
    event_type: str
    source: str
    step: Optional[int]
    payload: str  # JSON string


class EventPersister:
    def __init__(
        self,
        mysql_pool: AsyncMySQLPool,
        max_queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ):
        self._pool = mysql_pool
        self._queue: asyncio.Queue[Optional[_EventRow]] = asyncio.Queue(maxsize=max_queue_size)
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._worker_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._dropped_count = 0

    def enqueue(self, event: Dict[str, Any]) -> None:
        """将事件放入队列（非阻塞），队列满时 drop oldest。"""
        row = _EventRow(
            trace_id=event["trace_id"],
            sequence=event["sequence"],
            event_type=event["type"],
            source=event.get("source", "harness"),
            step=event.get("step"),
            payload=json.dumps(event.get("data", {}), ensure_ascii=False),
        )
        try:
            self._queue.put_nowait(row)
        except asyncio.QueueFull:
            # 背压策略: 丢弃最旧事件，放入新事件
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._dropped_count += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(row)
            except asyncio.QueueFull:
                self._dropped_count += 1

    async def start(self) -> None:
        """启动后台 worker。"""
        if self._worker_task is not None:
            return
        self._stopping = False
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self, grace_seconds: float = 5.0) -> None:
        """停止 worker，flush 剩余事件后退出。"""
        if self._worker_task is None:
            return
        self._stopping = True
        try:
            await asyncio.wait_for(self._worker_task, timeout=grace_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "EventPersister shutdown timed out after %.1fs, %d events may be lost",
                grace_seconds,
                self._queue.qsize(),
            )
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._worker_task = None

        if self._dropped_count > 0:
            logger.warning("EventPersister dropped %d events due to queue full", self._dropped_count)

    async def _worker(self) -> None:
        """后台消费循环: 攒批 → 写入 MySQL。"""
        batch: List[_EventRow] = []
        last_flush = asyncio.get_event_loop().time()

        while not self._stopping:
            elapsed = asyncio.get_event_loop().time() - last_flush
            timeout = max(0.05, self._flush_interval - elapsed)

            try:
                row = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                if row is None:  # 显式停止信号
                    break
                batch.append(row)
                self._queue.task_done()
            except asyncio.TimeoutError:
                pass

            if len(batch) >= self._batch_size or (
                batch and asyncio.get_event_loop().time() - last_flush >= self._flush_interval
            ):
                await self._flush(batch)
                batch.clear()
                last_flush = asyncio.get_event_loop().time()

        # 最后 flush 一次
        if batch:
            await self._flush(batch)

        # 排空队列中剩余事件（stop 被调用后 queue 中可能还有排队中的事件）
        drained: List[_EventRow] = []
        while not self._queue.empty():
            try:
                row = self._queue.get_nowait()
                if row is not None:
                    drained.append(row)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        if drained:
            await self._flush(drained)

    async def _flush(self, batch: List[_EventRow]) -> None:
        """批量写入 MySQL。"""
        params = [
            (r.trace_id, r.sequence, r.event_type, r.source, r.step, r.payload)
            for r in batch
        ]
        try:
            await self._pool.async_save(SQL_INSERT, params, batch=True)
        except Exception:
            logger.exception("EventPersister flush failed, %d events lost", len(batch))


__all__ = ["EventPersister"]
