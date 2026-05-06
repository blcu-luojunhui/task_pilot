"""
Agent Protocol - Message Formatting

This module handles message protocol and formatting:
- Tool call structures
- Assistant messages
- Tool result messages
"""

from .models import ToolCall
from .messages import (
    assistant_message,
    tool_result_message,
    get_tool_calls,
    normalize_tool_calls,
)

__all__ = [
    "ToolCall",
    "assistant_message",
    "tool_result_message",
    "get_tool_calls",
    "normalize_tool_calls",
]
