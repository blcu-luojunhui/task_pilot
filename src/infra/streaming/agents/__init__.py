"""
Agent Streaming Support

This module provides streaming capabilities for agent execution:
- Real-time output streaming
- Progress updates
- Event streaming
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


_stream_context: ContextVar[Optional["StreamContext"]] = ContextVar("stream_context", default=None)


@dataclass
class StreamContext:
    """Streaming context for current planner invocation."""

    trace_id: str
    step: int
    sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None


def set_stream_context(
    trace_id: str,
    step: int,
    sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
) -> None:
    """Set streaming context for current async task."""
    _stream_context.set(StreamContext(trace_id=trace_id, step=step, sink=sink))


def get_stream_context() -> Optional[StreamContext]:
    """Get current streaming context."""
    return _stream_context.get()


def clear_stream_context() -> None:
    """Clear streaming context."""
    _stream_context.set(None)


__all__ = [
    "StreamContext",
    "set_stream_context",
    "get_stream_context",
    "clear_stream_context",
]
