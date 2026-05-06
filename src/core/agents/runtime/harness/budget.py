"""
Budget controls for the agent loop harness.

The harness asks this layer whether another step or tool call is allowed.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.core.agents.state import AgentLoopState, StopReason


@dataclass(frozen=True)
class BudgetViolation:
    """A budget limit was reached."""

    stop_reason: StopReason
    event_name: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentBudget:
    """Resource budget for a single agent loop run."""

    max_steps: int = 8
    max_tool_calls: Optional[int] = None
    max_duration_seconds: Optional[float] = None

    def check_before_step(
        self,
        state: AgentLoopState,
        elapsed_seconds: float,
    ) -> Optional[BudgetViolation]:
        duration_violation = self._check_duration(elapsed_seconds)
        if duration_violation:
            return duration_violation

        if state.step >= self.max_steps:
            return BudgetViolation(
                stop_reason=StopReason.MAX_STEPS,
                event_name="max_steps_reached",
                detail={
                    "max_steps": self.max_steps,
                    "current_step": state.step,
                },
            )

        return None

    def check_after_step(
        self,
        state: AgentLoopState,
        elapsed_seconds: float,
    ) -> Optional[BudgetViolation]:
        if state.is_terminated():
            return None
        return self._check_duration(elapsed_seconds)

    def check_tool_calls(
        self,
        state: AgentLoopState,
        requested_tool_calls: int,
    ) -> Optional[BudgetViolation]:
        if self.max_tool_calls is None:
            return None

        used_tool_calls = len(state.tool_call_history)
        projected_tool_calls = used_tool_calls + requested_tool_calls
        if projected_tool_calls <= self.max_tool_calls:
            return None

        return BudgetViolation(
            stop_reason=StopReason.BUDGET_EXHAUSTED,
            event_name="budget_exhausted",
            detail={
                "budget": "max_tool_calls",
                "max_tool_calls": self.max_tool_calls,
                "used_tool_calls": used_tool_calls,
                "requested_tool_calls": requested_tool_calls,
            },
        )

    def _check_duration(self, elapsed_seconds: float) -> Optional[BudgetViolation]:
        if self.max_duration_seconds is None:
            return None
        if elapsed_seconds <= self.max_duration_seconds:
            return None

        return BudgetViolation(
            stop_reason=StopReason.BUDGET_EXHAUSTED,
            event_name="budget_exhausted",
            detail={
                "budget": "max_duration_seconds",
                "max_duration_seconds": self.max_duration_seconds,
                "elapsed_seconds": elapsed_seconds,
            },
        )


__all__ = ["AgentBudget", "BudgetViolation"]
