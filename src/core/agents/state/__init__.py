"""
State Layer - 状态层

提供 Agent 系统的状态管理和基础设施：
- state: 状态管理
- protocol: 消息协议
- context: 上下文管理
- memory: 记忆管理
"""

from .models import (
    AgentState,
    StateTransition,
    StopReason,
    ToolCallRecord,
    AgentLoopState,
    AgentLoopResult,
)
from .utils import generate_agent_trace_id
from .protocol import (
    ToolCall,
    assistant_message,
    tool_result_message,
    get_tool_calls,
    normalize_tool_calls,
)
from .context import ContextWindowManager
from .memory import ShortTermMemory, LongTermMemory, MemoryEntry
from .snapshot import StateSnapshot

__all__ = [
    # State
    "AgentState",
    "StateTransition",
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
    # Memory
    "ShortTermMemory",
    "LongTermMemory",
    "MemoryEntry",
    # Snapshot
    "StateSnapshot",
]
