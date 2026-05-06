"""State models for agent execution"""

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class StopReason(str, Enum):
    """Reasons for agent loop termination"""
    MAX_ITERATIONS = "max_iterations"
    END_TURN = "end_turn"
    ERROR = "error"
    BUDGET_EXCEEDED = "budget_exceeded"
    USER_INTERRUPT = "user_interrupt"
    CONSTRAINT_VIOLATION = "constraint_violation"


@dataclass
class ToolCallRecord:
    """Record of a tool call execution"""
    tool_name: str
    tool_input: dict
    tool_output: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: Optional[float] = None


@dataclass
class AgentLoopState:
    """State of the agent loop execution"""
    trace_id: str
    iteration: int = 0
    messages: List[dict] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    stop_reason: Optional[StopReason] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentLoopResult:
    """Result of agent loop execution"""
    state: AgentLoopState
    success: bool
    final_output: Optional[str] = None
    error: Optional[str] = None
