"""
Agent loop runner.

Runner assembles Think/Act/Observe and delegates lifecycle to a harness.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.loop.act import Act
from src.core.agents.loop.harness import (
    AgentBudget,
    AgentLoopHarness,
    ConstraintSet,
    ContinuousImprovement,
    FeedbackLoop,
    HarnessHook,
    WorkflowController,
)
from src.core.agents.loop.observe import Observe
from src.core.agents.loop.state import AgentLoopResult
from src.core.agents.loop.think import AssistantPlanner, Think
from src.core.agents.skills import SkillContext, SkillExecutor, SkillRegistry


@dataclass
class AgentLoopRunner:
    """Agent loop runner that assembles stages and delegates lifecycle to a harness."""

    planner: AssistantPlanner
    registry: SkillRegistry
    executor: SkillExecutor
    max_steps: int = 8
    abort_on_tool_error: bool = True
    is_cancelled: Optional[Callable[[], bool]] = None
    tool_dependencies: Optional[Mapping[str, Any]] = None
    context_builder: Optional[Callable[[Any], SkillContext]] = None
    thinker: Optional[Think] = None
    actor: Optional[Act] = None
    observer: Optional[Observe] = None
    harness: Optional[AgentLoopHarness] = None
    hooks: Optional[List[HarnessHook]] = None
    budget: Optional[AgentBudget] = None
    constraints: Optional[ConstraintSet] = None
    feedback_loop: Optional[FeedbackLoop] = None
    continuous_improvement: Optional[ContinuousImprovement] = None
    workflow: Optional[WorkflowController] = None

    def __post_init__(self) -> None:
        if self.budget is None:
            self.budget = AgentBudget(max_steps=self.max_steps)
        if self.constraints is None:
            self.constraints = ConstraintSet()
        if self.feedback_loop is None:
            self.feedback_loop = FeedbackLoop()
        if self.continuous_improvement is None:
            self.continuous_improvement = ContinuousImprovement()
        if self.thinker is None:
            self.thinker = Think(self.planner)
        if self.actor is None:
            self.actor = Act(
                registry=self.registry,
                executor=self.executor,
                tool_dependencies=self.tool_dependencies,
                context_builder=self.context_builder,
            )
        if self.observer is None:
            self.observer = Observe(abort_on_tool_error=self.abort_on_tool_error)
        if self.harness is None:
            self.harness = AgentLoopHarness(
                thinker=self.thinker,
                actor=self.actor,
                observer=self.observer,
                budget=self.budget,
                is_cancelled=self.is_cancelled,
                hooks=list(self.hooks or []),
                constraints=self.constraints,
                feedback_loop=self.feedback_loop,
                continuous_improvement=self.continuous_improvement,
                workflow=self.workflow,
            )

    async def run(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentLoopResult:
        return await self.harness.run(
            goal=goal,
            messages=messages,
            metadata=metadata,
            trace_id=trace_id,
        )


__all__ = ["AgentLoopRunner"]
