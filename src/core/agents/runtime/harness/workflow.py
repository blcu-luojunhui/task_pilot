"""
Workflow control for the agent loop harness.

This layer centralizes decisions about whether the loop may continue.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.core.agents.runtime.harness.budget import AgentBudget, BudgetViolation
from src.core.agents.runtime.harness.constraints import ConstraintSet, ConstraintViolation
from src.core.agents.state.protocol import get_tool_calls
from src.core.agents.state import AgentLoopState, StopReason


@dataclass(frozen=True)
class WorkflowDecision:
    """A workflow decision that stops the current run."""

    stop_reason: StopReason
    event_name: str
    detail: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_budget(cls, violation: BudgetViolation) -> "WorkflowDecision":
        return cls(
            stop_reason=violation.stop_reason,
            event_name=violation.event_name,
            detail=violation.detail,
        )

    @classmethod
    def from_constraint(cls, violation: ConstraintViolation) -> "WorkflowDecision":
        detail = dict(violation.detail)
        detail.setdefault("message", violation.message)
        return cls(
            stop_reason=violation.stop_reason,
            event_name=violation.event_name,
            detail=detail,
        )


@dataclass
class WorkflowController:
    """Controls loop progression using cancellation, budget, and constraints."""

    budget: AgentBudget
    is_cancelled: Optional[Callable[[], bool]] = None
    constraints: ConstraintSet = field(default_factory=ConstraintSet)

    def before_step(
        self,
        state: AgentLoopState,
        elapsed_seconds: float,
    ) -> Optional[WorkflowDecision]:
        violation = self.constraints.check(
            "before_step",
            state,
            {"elapsed_seconds": elapsed_seconds},
        )
        if violation:
            return WorkflowDecision.from_constraint(violation)

        budget_violation = self.budget.check_before_step(state, elapsed_seconds)
        if budget_violation:
            return WorkflowDecision.from_budget(budget_violation)

        if self.is_cancelled and self.is_cancelled():
            return WorkflowDecision(
                stop_reason=StopReason.CANCELLED,
                event_name="run_cancelled",
            )

        return None

    def after_think(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
    ) -> Optional[WorkflowDecision]:
        violation = self.constraints.check(
            "after_think",
            state,
            {"assistant_message": assistant_message},
        )
        if violation:
            return WorkflowDecision.from_constraint(violation)
        return None

    def before_act(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
    ) -> Optional[WorkflowDecision]:
        tool_calls = get_tool_calls(assistant_message)
        violation = self.constraints.check(
            "before_act",
            state,
            {
                "assistant_message": assistant_message,
                "tool_calls": [call.to_dict() for call in tool_calls],
            },
        )
        if violation:
            return WorkflowDecision.from_constraint(violation)

        budget_violation = self.budget.check_tool_calls(state, len(tool_calls))
        if budget_violation:
            return WorkflowDecision.from_budget(budget_violation)

        return None

    def after_step(
        self,
        state: AgentLoopState,
        elapsed_seconds: float,
        assistant_message: Dict[str, Any],
        tool_results: list[Dict[str, Any]],
    ) -> Optional[WorkflowDecision]:
        if state.is_terminated():
            return None

        violation = self.constraints.check(
            "after_step",
            state,
            {
                "elapsed_seconds": elapsed_seconds,
                "assistant_message": assistant_message,
                "tool_results": tool_results,
            },
        )
        if violation:
            return WorkflowDecision.from_constraint(violation)

        budget_violation = self.budget.check_after_step(state, elapsed_seconds)
        if budget_violation:
            return WorkflowDecision.from_budget(budget_violation)

        return None


__all__ = ["WorkflowController", "WorkflowDecision"]
