"""Message formatting utilities"""

import json
from typing import Any, Dict, List, Optional

from .models import ToolCall


def assistant_message(content: str, tool_calls: Optional[List[ToolCall]] = None) -> Dict[str, Any]:
    """Create an assistant message"""
    message = {
        "role": "assistant",
        "content": content,
    }
    if tool_calls:
        message["tool_calls"] = [tc.to_dict() for tc in tool_calls]
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
    """
    从 assistant message 中提取 tool calls

    自动兼容 OpenAI/Claude/标准格式
    """
    raw_calls = message.get("tool_calls")
    if not raw_calls:
        return []

    return [ToolCall.from_raw(tc) for tc in raw_calls]


def normalize_tool_calls(tool_calls: Any) -> List[ToolCall]:
    """
    将任意格式的 tool_calls 标准化为 ToolCall 列表

    支持：
    - List[ToolCall] (已标准化)
    - List[Dict] (原始 LLM 响应)
    - None / 空
    """
    if not tool_calls:
        return []

    result = []
    for tc in tool_calls:
        if isinstance(tc, ToolCall):
            result.append(tc)
        elif isinstance(tc, dict):
            result.append(ToolCall.from_raw(tc))
    return result
