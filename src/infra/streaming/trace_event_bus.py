from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional


@dataclass
class TraceSubscription:
    trace_id: str
    queue: asyncio.Queue


@dataclass
class _TraceStream:
    sequence: int = 0
    replay: Deque[Dict[str, Any]] = field(default_factory=deque)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    closed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TraceEventBus:
    def __init__(
        self,
        replay_limit: int = 200,
        subscriber_queue_size: int = 200,
        closed_ttl_seconds: int = 300,
    ):
        self._traces: Dict[str, _TraceStream] = {}
        self._replay_limit = replay_limit
        self._subscriber_queue_size = subscriber_queue_size
        self._closed_ttl_seconds = closed_ttl_seconds

    def ensure_trace(self, trace_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        stream = self._traces.get(trace_id)
        if stream is None:
            self._traces[trace_id] = _TraceStream(metadata=dict(metadata or {}))
            return
        if metadata:
            stream.metadata.update(metadata)

    def has_trace(self, trace_id: str) -> bool:
        return trace_id in self._traces

    def is_closed(self, trace_id: str) -> bool:
        stream = self._traces.get(trace_id)
        return bool(stream and stream.closed)

    def publish(
        self,
        trace_id: str,
        event_type: str,
        data: Dict[str, Any],
        source: str,
        step: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.ensure_trace(trace_id)
        stream = self._traces[trace_id]
        stream.sequence += 1
        event = {
            "sequence": stream.sequence,
            "type": event_type,
            "trace_id": trace_id,
            "step": step,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        stream.replay.append(event)
        while len(stream.replay) > self._replay_limit:
            stream.replay.popleft()

        dead_subscribers = []
        for queue in stream.subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_subscribers.append(queue)

        for queue in dead_subscribers:
            stream.subscribers.discard(queue)

        return event

    def subscribe(
        self,
        trace_id: str,
        after_sequence: Optional[int] = None,
    ) -> TraceSubscription:
        if trace_id not in self._traces:
            raise KeyError(trace_id)

        stream = self._traces[trace_id]
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._subscriber_queue_size)
        for event in stream.replay:
            if after_sequence is None or event["sequence"] > after_sequence:
                queue.put_nowait(event)
        stream.subscribers.add(queue)
        return TraceSubscription(trace_id=trace_id, queue=queue)

    def unsubscribe(self, subscription: TraceSubscription) -> None:
        stream = self._traces.get(subscription.trace_id)
        if not stream:
            return
        stream.subscribers.discard(subscription.queue)

    def close_trace(self, trace_id: str) -> None:
        stream = self._traces.get(trace_id)
        if not stream:
            return
        stream.closed = True
        stream.closed_at = datetime.now(timezone.utc)

    def prune_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = []
        for trace_id, stream in self._traces.items():
            if not stream.closed or not stream.closed_at:
                continue
            if now - stream.closed_at > timedelta(seconds=self._closed_ttl_seconds):
                expired.append(trace_id)
        for trace_id in expired:
            del self._traces[trace_id]
        return len(expired)


__all__ = ["TraceEventBus", "TraceSubscription"]
