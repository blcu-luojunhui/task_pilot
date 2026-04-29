from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class StopReason(str, Enum):
    MODEL_FINAL = "model_final"
    MAX_STEPS = "max_steps"
    CANCELLED = "cancelled"
    TOOL_ERROR_ABORT = "tool_error_abort"
    LLM_ERROR_ABORT = "llm_error_abort"


@dataclass
class ToolCallRecord:
    step: int
    tool_call_id: str
    tool_name: str
    arguments: dict
    status: str
    result: Any = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AgentLoopState:
    goal: str
    messages: list[dict]
    max_steps: int
    step: int = 0
    tool_call_history: list[ToolCallRecord] = field(default_factory=list)
    stop_reason: Optional[StopReason] = None
    final_answer: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "messages": self.messages,
            "max_steps": self.max_steps,
            "step": self.step,
            "tool_call_history": [record.to_dict() for record in self.tool_call_history],
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "final_answer": self.final_answer,
        }

    def add_assistant_message(self, message: dict) -> None:
        self.messages.append(message)

    def add_tool_results(self, results: list[dict]) -> None:
        self.messages.extend(results)

    def is_terminated(self) -> bool:
        return self.stop_reason is not None


@dataclass
class AgentLoopResult:
    success: bool
    final_answer: Optional[str]
    stop_reason: StopReason
    total_steps: int
    tool_calls_count: int
    duration_seconds: float

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "stop_reason": self.stop_reason.value,
            "total_steps": self.total_steps,
            "tool_calls_count": self.tool_calls_count,
            "duration_seconds": self.duration_seconds,
        }
