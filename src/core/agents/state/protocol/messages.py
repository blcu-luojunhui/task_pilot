"""Message formatting utilities"""

from typing import Any, Dict, List, Optional

from .models import ToolCall


def assistant_message(content: str, tool_calls: Optional[List[ToolCall]] = None) -> Dict[str, Any]:
    """Create an assistant message"""
    message = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": tc.input,
                }
            }
            for tc in tool_calls
        ]
    return message


def tool_result_message(tool_call_id: str, content: str, is_error: bool = False) -> Dict[str, Any]:
    """Create a tool result message"""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
        "is_error": is_error,
    }


def get_tool_calls(message: Dict[str, Any]) -> List[ToolCall]:
    """Extract tool calls from a message"""
    if "tool_calls" not in message:
        return []

    tool_calls = []
    for tc in message["tool_calls"]:
        if tc.get("type") == "function":
            func = tc["function"]
            tool_calls.append(ToolCall(
                id=tc["id"],
                name=func["name"],
                input=func.get("arguments", {})
            ))
    return tool_calls


def normalize_tool_calls(tool_calls: Any) -> List[ToolCall]:
    """Normalize tool calls from various formats"""
    if not tool_calls:
        return []

    if isinstance(tool_calls, list):
        return [
            tc if isinstance(tc, ToolCall) else ToolCall(**tc)
            for tc in tool_calls
        ]

    return []
