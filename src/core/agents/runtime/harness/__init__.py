"""
Harness layer for the agent loop.

The harness owns lifecycle concerns: run context, step boundaries, events,
hooks, cancellation checks, and final result building. Think/Act/Observe stay
focused on their own stage logic.
"""

from .harness import (
    HarnessEvent,
    HarnessHook,
    AgentRunContext,
    AgentLoopHarness,
)
from .budget import AgentBudget, BudgetViolation
from .constraints import ConstraintSet, ConstraintViolation
from .feedback import FeedbackLoop
from .improvement import (
    ContinuousImprovement,
    DBImprovementStore,
    ImprovementRecord,
    InMemoryImprovementStore,
)
from .logging import HarnessEventLogger
from .workflow import WorkflowController, WorkflowDecision
from .reflection import ReflectionProvider
from .approval import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPolicyError,
    ApprovalRequest,
)
from .reconciliation import ReconciliationDecision, ReconciliationError

__all__ = [
    "HarnessEvent",
    "HarnessHook",
    "AgentRunContext",
    "AgentLoopHarness",
    "AgentBudget",
    "BudgetViolation",
    "ConstraintSet",
    "ConstraintViolation",
    "FeedbackLoop",
    "ContinuousImprovement",
    "DBImprovementStore",
    "ImprovementRecord",
    "InMemoryImprovementStore",
    "HarnessEventLogger",
    "WorkflowController",
    "WorkflowDecision",
    "ReflectionProvider",
    "ApprovalDecision",
    "ApprovalPolicy",
    "ApprovalPolicyError",
    "ApprovalRequest",
    "ReconciliationDecision",
    "ReconciliationError",
]
