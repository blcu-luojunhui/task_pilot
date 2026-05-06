"""
Foundation Layer - 基础层

提供 Agent 系统的核心抽象和基础设施：
- state: 状态管理
- protocol: 消息协议
- context: 上下文管理
"""

from .state import (
    StopReason,
    ToolCallRecord,
    AgentLoopState,
    AgentLoopResult,
    generate_agent_trace_id,
)
from .protocol import (
    ToolCall,
    assistant_message,
    tool_result_message,
    get_tool_calls,
    normalize_tool_calls,
)
from .context import ContextWindowManager

__all__ = [
    # State
    "StopReason",
    "ToolCallRecord",
    "AgentLoopState",
    "AgentLoopResult",
    "generate_agent_trace_id",
    # Protocol
    "ToolCall",
    "assistant_message",
    "tool_result_message",
    "get_tool_calls",
    "normalize_tool_calls",
    # Context
    "ContextWindowManager",
]
