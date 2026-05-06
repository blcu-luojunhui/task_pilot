"""Agent loop runner implementation"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.loop.act import Act
from src.core.agents.context import ContextWindowManager
from src.core.agents.runtime.harness import (
    AgentBudget,
    AgentLoopHarness,
    ConstraintSet,
    ContinuousImprovement,
    FeedbackLoop,
    HarnessHook,
    WorkflowController,
)
from src.core.agents.loop.observe import Observe
from src.core.agents.routing.router import TaskRouter
from src.core.agents.state import AgentLoopResult, StopReason
from src.core.agents.loop.think import AssistantPlanner, Think
from src.core.agents.loop.think.knowledge_selector import KnowledgeSelector
from src.core.agents.loop.think.prompt_assembler import PromptAssembler
from src.core.agents.skills import SkillContext, SkillExecutor, SkillRegistry
from src.core.agents.skills.guard import PermissionGuard


@dataclass
class AgentLoopRunner:
    """Agent loop runner that assembles stages and delegates lifecycle to a harness."""

    planner: AssistantPlanner
    registry: SkillRegistry
    executor: SkillExecutor
    max_steps: int = 8
    abort_on_tool_error: bool = False
    max_tool_result_length: int = 2000
    max_consecutive_errors: int = 3
    max_context_tokens: int = 60000
    permission_guard: Optional[PermissionGuard] = None
    router: Optional[TaskRouter] = None
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
            context_manager = ContextWindowManager(
                max_context_tokens=self.max_context_tokens,
            )
            knowledge_selector = KnowledgeSelector(self.registry)
            prompt_assembler = PromptAssembler(knowledge_selector=knowledge_selector)
            self.thinker = Think(
                self.planner,
                context_manager=context_manager,
                prompt_assembler=prompt_assembler,
            )
        if self.actor is None:
            self.actor = Act(
                registry=self.registry,
                executor=self.executor,
                tool_dependencies=self.tool_dependencies,
                context_builder=self.context_builder,
                max_tool_result_length=self.max_tool_result_length,
                permission_guard=self.permission_guard,
            )
        if self.observer is None:
            self.observer = Observe(
                abort_on_tool_error=self.abort_on_tool_error,
                max_consecutive_errors=self.max_consecutive_errors,
            )
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
        if self.router is None:
            self.router = TaskRouter(planner=self.planner)

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

    async def run_with_routing(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentLoopResult:
        if not self.router:
            return await self.run(goal=goal, messages=messages, metadata=metadata, trace_id=trace_id)

        sub_goals = await self.router.route(goal)
        if len(sub_goals) <= 1:
            return await self.run(goal=goal, messages=messages, metadata=metadata, trace_id=trace_id)

        accumulated_messages = list(messages or [])
        results: List[str] = []
        last_result: Optional[AgentLoopResult] = None

        for index, sub_goal in enumerate(sub_goals, start=1):
            run_messages = list(accumulated_messages)
            if results:
                run_messages.append({
                    "role": "system",
                    "content": "Previous sub-goal results:\n" + "\n".join(results),
                })
            run_messages.append({
                "role": "system",
                "content": f"Current sub-goal {index}/{len(sub_goals)}: {sub_goal}",
            })
            last_result = await self.run(
                goal=sub_goal,
                messages=run_messages,
                metadata=metadata,
                trace_id=trace_id,
            )
            results.append(last_result.final_answer or "")

            if not last_result.success:
                return last_result

        assert last_result is not None
        return AgentLoopResult(
            trace_id=last_result.trace_id,
            success=True,
            final_answer="\n\n".join(result for result in results if result),
            stop_reason=StopReason.MODEL_FINAL,
            total_steps=sum(1 for _ in sub_goals),
            tool_calls_count=last_result.tool_calls_count,
            duration_seconds=last_result.duration_seconds,
        )
