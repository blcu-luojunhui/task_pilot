"""
Agent State Management

This module manages agent execution state, including:
- Loop state tracking
- Stop reasons
- Tool call records
- Execution results
"""

from .models import (
    StopReason,
    ToolCallRecord,
    AgentLoopState,
    AgentLoopResult,
)
from src.infra.shared import generate_agent_trace_id

__all__ = [
    "StopReason",
    "ToolCallRecord",
    "AgentLoopState",
    "AgentLoopResult",
    "generate_agent_trace_id",
]
