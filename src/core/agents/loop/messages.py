"""
Message primitives for the agent loop.

The runtime still accepts plain dictionaries for adapter compatibility, but all
loop stages should use these helpers instead of re-encoding message conventions.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ToolCall:
    """Normalized tool call emitted by a model."""

    id: str
    name: str
    arguments: Any = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            arguments=data.get("arguments", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def assistant_message(
    content: Optional[str],
    tool_calls: Optional[Iterable[ToolCall | Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Create an assistant message in the internal loop shape."""
    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content,
    }
    normalized_tool_calls = normalize_tool_calls(tool_calls or [])
    if normalized_tool_calls:
        message["tool_calls"] = [call.to_dict() for call in normalized_tool_calls]
    return message


def tool_result_message(
    tool_call_id: str,
    name: str,
    content: Any,
    is_error: bool = False,
) -> Dict[str, Any]:
    """Create a tool result message in the internal loop shape."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": serialize_content(content),
        "is_error": is_error,
    }


def normalize_tool_calls(
    tool_calls: Iterable[ToolCall | Dict[str, Any]],
) -> List[ToolCall]:
    """Normalize model tool calls into ToolCall objects."""
    normalized = []
    for call in tool_calls:
        if isinstance(call, ToolCall):
            normalized.append(call)
        else:
            normalized.append(ToolCall.from_dict(call))
    return normalized


def get_tool_calls(message: Optional[Dict[str, Any]]) -> List[ToolCall]:
    """Extract normalized tool calls from an assistant message."""
    if not message:
        return []
    return normalize_tool_calls(message.get("tool_calls") or [])


def serialize_content(value: Any) -> str:
    """Serialize tool output into transcript-safe string content."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


__all__ = [
    "ToolCall",
    "assistant_message",
    "get_tool_calls",
    "normalize_tool_calls",
    "serialize_content",
    "tool_result_message",
]
