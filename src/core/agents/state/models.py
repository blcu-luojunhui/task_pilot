"""State models for agent execution"""

from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class AgentState(str, Enum):
    """Agent 生命周期状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class StateTransition:
    """状态转换记录"""
    from_state: AgentState
    to_state: AgentState
    timestamp: datetime = field(default_factory=datetime.now)
    reason: Optional[str] = None


class StopReason(str, Enum):
    """Agent loop 终止原因"""
    # 正常终止
    MODEL_FINAL = "model_final"             # 模型给出最终答案
    # 预算/限制
    MAX_STEPS = "max_steps"                 # 达到最大步数
    BUDGET_EXHAUSTED = "budget_exhausted"   # 预算耗尽
    # 错误
    LLM_ERROR_ABORT = "llm_error_abort"     # LLM 调用失败
    TOOL_ERROR_ABORT = "tool_error_abort"   # 工具连续失败
    ERROR = "error"                         # 未知错误
    # 外部控制
    USER_CANCELLED = "user_cancelled"       # 用户取消
    CONSTRAINT_VIOLATION = "constraint_violation"  # 约束违反


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Optional[str] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: Optional[float] = None


@dataclass
class AgentLoopState:
    """Agent loop 运行状态"""

    goal: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_steps: int = 8
    trace_id: str = ""

    # 运行时状态
    step: int = 0
    stop_reason: Optional[StopReason] = None
    final_answer: Optional[str] = None
    consecutive_tool_errors: int = 0

    # 工具调用记录
    tool_calls: List[ToolCallRecord] = field(default_factory=list)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def tool_call_history(self) -> List[ToolCallRecord]:
        """工具调用历史（别名）"""
        return self.tool_calls

    def is_terminated(self) -> bool:
        """是否已终止"""
        return self.stop_reason is not None

    def add_assistant_message(self, message: Dict[str, Any]) -> None:
        """添加 assistant 消息"""
        self.messages.append(message)

    def add_tool_results(self, results: List[Dict[str, Any]]) -> None:
        """添加工具执行结果到消息历史"""
        for result in results:
            self.messages.append(result)


@dataclass
class AgentLoopResult:
    """Agent loop 执行结果"""
    trace_id: str = ""
    success: bool = False
    final_answer: Optional[str] = None
    stop_reason: Optional[StopReason] = None
    total_steps: int = 0
    tool_calls_count: int = 0
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
