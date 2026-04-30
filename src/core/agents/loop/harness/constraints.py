"""
Constraint checks for the agent loop harness.

Constraints are policy gates. They can inspect the current state plus a phase
payload and stop the workflow before unsafe or unwanted work is performed.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.loop.state import AgentLoopState, StopReason


@dataclass(frozen=True)
class ConstraintViolation:
    """A harness constraint blocked the workflow."""

    message: str
    stop_reason: StopReason = StopReason.CONSTRAINT_VIOLATION
    event_name: str = "constraint_violation"
    detail: Dict[str, Any] = field(default_factory=dict)


ConstraintCheck = Callable[
    [AgentLoopState, Dict[str, Any]],
    Optional[ConstraintViolation],
]


@dataclass
class ConstraintSet:
    """Phase-based collection of constraint checks."""

    checks: Mapping[str, List[ConstraintCheck]] = field(default_factory=dict)

    def check(
        self,
        phase: str,
        state: AgentLoopState,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[ConstraintViolation]:
        for check in self.checks.get(phase, []):
            violation = check(state, payload or {})
            if violation:
                return violation
        return None


__all__ = ["ConstraintCheck", "ConstraintSet", "ConstraintViolation"]
