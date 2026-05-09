"""
Harness layer for the agent loop.

The harness owns lifecycle concerns: run context, step boundaries, events,
hooks, cancellation checks, and final result building. Think/Act/Observe stay
focused on their own stage logic.
"""

import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from typing import TYPE_CHECKING

from src.core.agents.engine.loop import Act
from src.core.agents.engine.types import (
    ActionType,
    ThoughtType,
    Thought,
    Action,
    Observation,
    Step,
)
from src.core.agents.runtime.harness.budget import AgentBudget, BudgetViolation
from src.core.agents.runtime.harness.constraints import ConstraintSet, ConstraintViolation
from src.core.agents.runtime.harness.feedback import FeedbackLoop
from src.core.agents.runtime.harness.improvement import (
    ContinuousImprovement,
    ImprovementRecord,
    InMemoryImprovementStore,
)
from src.core.agents.runtime.harness.logging import HarnessEventLogger
from src.core.agents.runtime.harness.workflow import WorkflowController, WorkflowDecision
from src.core.agents.state.protocol import get_tool_calls
from src.core.agents.engine.loop import Observe
from src.core.agents.state import (
    AgentLoopResult,
    AgentLoopState,
    AgentState,
    StopReason,
    generate_agent_trace_id,
)
from src.core.agents.engine.loop import Think

if TYPE_CHECKING:
    from src.core.agents.engine.lifecycle import LifecycleManager


@dataclass
class HarnessEvent:
    """Event emitted by the harness lifecycle."""

    name: str
    state: AgentLoopState
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def trace_id(self) -> str:
        return self.state.trace_id


HarnessHook = Callable[[HarnessEvent], Any]


@dataclass
class AgentRunContext:
    """Mutable context owned by one harness run."""

    state: AgentLoopState
    started_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentLoopHarness:
    """Lifecycle harness that drives Think -> Act -> Observe."""

    thinker: Think
    actor: Act
    observer: Observe
    budget: AgentBudget
    is_cancelled: Optional[Callable[[], bool]] = None
    hooks: List[HarnessHook] = field(default_factory=list)
    constraints: ConstraintSet = field(default_factory=ConstraintSet)
    feedback_loop: FeedbackLoop = field(default_factory=FeedbackLoop)
    continuous_improvement: ContinuousImprovement = field(default_factory=ContinuousImprovement)
    workflow: Optional[WorkflowController] = None
    event_logger: HarnessEventLogger = field(default_factory=HarnessEventLogger)
    lifecycle: "Optional[LifecycleManager]" = None

    def __post_init__(self) -> None:
        if self.workflow is None:
            self.workflow = WorkflowController(
                budget=self.budget,
                is_cancelled=self.is_cancelled,
                constraints=self.constraints,
            )

    async def run(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentLoopResult:
        run_metadata = dict(metadata or {})
        run_trace_id = trace_id or run_metadata.get("trace_id") or generate_agent_trace_id()
        run_metadata["trace_id"] = run_trace_id

        context = AgentRunContext(
            state=AgentLoopState(
                goal=goal,
                messages=list(messages or []),
                max_steps=self.budget.max_steps,
                trace_id=run_trace_id,
            ),
            started_at=time.monotonic(),
            metadata=run_metadata,
        )
        state = context.state

        try:
            await self._emit("run_start", state, {"metadata": context.metadata})

            # 同步 lifecycle 初始状态
            if self.lifecycle:
                self.lifecycle.current_loop_state = state
                if self.lifecycle.state == AgentState.IDLE:
                    self.lifecycle.transition_to(AgentState.RUNNING, reason="harness start")
                # 如果已在 RUNNING 状态（Agent.run() 可能预先设置了），不再重复转换
                state.lifecycle_state = self.lifecycle.state

            while not state.is_terminated():
                # 生命周期检查：暂停 / 停止
                if self.lifecycle:
                    self.lifecycle.current_loop_state = state
                    state.lifecycle_state = self.lifecycle.state
                    await self.lifecycle.wait_if_paused()
                    if self.lifecycle.is_stop_requested():
                        state.stop_reason = StopReason.USER_CANCELLED
                        state.lifecycle_state = self.lifecycle.state
                        await self._emit("run_stopped", state)
                        break
                    state.lifecycle_state = self.lifecycle.state

                decision = self.workflow.before_step(state, self._elapsed_seconds(context))
                if decision:
                    await self._apply_workflow_decision(state, decision)
                    break

                state.step += 1
                await self._emit("step_start", state)

                assistant_message = await self._think(state)
                if state.is_terminated() or assistant_message is None:
                    break

                decision = self.workflow.after_think(state, assistant_message)
                if decision:
                    # 记录 Step 后再终止
                    step_records = self._build_step_records(state, assistant_message, [])
                    state.steps.extend(step_records)
                    await self._apply_workflow_decision(state, decision)
                    break

                tool_results = []
                decision = self.workflow.before_act(state, assistant_message)
                if decision:
                    self._observe(state, assistant_message, tool_results)
                    # 记录 Step（工具调用被约束阻止）
                    step_records = self._build_step_records(state, assistant_message, tool_results)
                    state.steps.extend(step_records)
                    await self._apply_workflow_decision(state, decision)
                    break
                else:
                    tool_results = await self._act(state, assistant_message)
                    self._observe(state, assistant_message, tool_results)

                feedback_messages = await self.feedback_loop.run(
                    state,
                    {
                        "assistant_message": assistant_message,
                        "tool_results": tool_results,
                    },
                )
                if feedback_messages:
                    await self._emit(
                        "feedback_collected",
                        state,
                        {"messages": feedback_messages},
                    )

                decision = self.workflow.after_step(
                    state,
                    self._elapsed_seconds(context),
                    assistant_message,
                    tool_results,
                )
                if decision:
                    await self._apply_workflow_decision(state, decision)

                # 构建结构化 Step 记录（并行工具调用各自一个 Step）
                step_records = self._build_step_records(state, assistant_message, tool_results)
                state.steps.extend(step_records)

                await self._emit(
                    "step_end",
                    state,
                    {
                        "assistant_message": assistant_message,
                        "tool_results": tool_results,
                    },
                )

        except Exception as e:
            logger.exception(f"Agent loop crashed at step {state.step}: {e}")
            if not state.stop_reason:
                state.stop_reason = StopReason.ERROR
            if self.lifecycle:
                state.lifecycle_state = self.lifecycle.state
            await self._emit("run_error", state, {"error": str(e)})

        if self.lifecycle:
            self.lifecycle.current_loop_state = state
            state.lifecycle_state = self.lifecycle.state
        result = self._build_result(context)
        improvement_record = await self.continuous_improvement.capture(
            state,
            result,
            context.metadata,
        )
        if improvement_record:
            await self._emit(
                "improvement_recorded",
                state,
                {"record": improvement_record},
            )
        await self._emit("run_end", state, {"result": result})
        return result

    async def _think(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        await self._emit("think_start", state)
        assistant_message = await self.thinker.run(state)
        await self._emit("think_end", state, {"assistant_message": assistant_message})
        return assistant_message

    async def _act(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        tool_calls = get_tool_calls(assistant_message)
        if not tool_calls:
            return []

        await self._emit(
            "act_start",
            state,
            {"tool_calls": [call.to_dict() for call in tool_calls]},
        )
        tool_results = await self.actor.run(state, tool_calls)
        await self._emit("act_end", state, {"tool_results": tool_results})
        return tool_results

    def _observe(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> None:
        self.observer.run(state, assistant_message, tool_results)

    def _build_step_records(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> List[Step]:
        """从 Think-Act-Observe 数据构建结构化 Step 记录（支持并行工具调用）"""
        content = assistant_message.get("content") or ""
        tool_calls = get_tool_calls(assistant_message)

        # 判断思考类型
        if content and tool_calls:
            thought_type = ThoughtType.PLANNING
        elif content:
            thought_type = ThoughtType.REASONING
        else:
            thought_type = ThoughtType.REASONING

        thought = Thought(type=thought_type, content=content)
        steps: List[Step] = []

        if tool_calls:
            for tc in tool_calls:
                action = Action(
                    type=ActionType.TOOL_CALL,
                    target=tc.name,
                    parameters=tc.arguments,
                )
                matching = next(
                    (r for r in tool_results if r.get("tool_call_id") == tc.id), {}
                )
                result_content = str(matching.get("content", ""))
                is_error = result_content.startswith("Error:")
                observation = Observation(
                    action=action,
                    result=result_content,
                    success=not is_error,
                    error=result_content if is_error else None,
                )
                steps.append(
                    Step(
                        step_number=state.step,
                        thought=thought if len(steps) == 0 else None,
                        action=action,
                        observation=observation,
                    )
                )
        elif content:
            action = Action(
                type=ActionType.ANSWER,
                target="final",
                parameters={"content": content},
            )
            observation = Observation(
                action=action,
                result=content,
                success=True,
            )
            steps.append(
                Step(
                    step_number=state.step,
                    thought=thought,
                    action=action,
                    observation=observation,
                )
            )

        return steps

    def _build_result(self, context: AgentRunContext) -> AgentLoopResult:
        state = context.state
        # 从结构化 Step 记录中统计 tool calls
        tool_call_steps = [
            s for s in state.steps if s.action and s.action.type == ActionType.TOOL_CALL
        ]
        return AgentLoopResult(
            trace_id=state.trace_id,
            success=state.stop_reason == StopReason.MODEL_FINAL,
            final_answer=state.final_answer,
            stop_reason=state.stop_reason,
            total_steps=state.step,
            tool_calls_count=len(tool_call_steps),
            duration_seconds=time.monotonic() - context.started_at,
        )

    async def _apply_budget_violation(
        self,
        state: AgentLoopState,
        violation: BudgetViolation,
    ) -> None:
        state.stop_reason = violation.stop_reason
        await self._emit(violation.event_name, state, violation.detail)

    async def _apply_workflow_decision(
        self,
        state: AgentLoopState,
        decision: WorkflowDecision,
    ) -> None:
        state.stop_reason = decision.stop_reason
        await self._emit(decision.event_name, state, decision.detail)

    def _elapsed_seconds(self, context: AgentRunContext) -> float:
        return time.monotonic() - context.started_at

    async def _emit(
        self,
        name: str,
        state: AgentLoopState,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = HarnessEvent(name=name, state=state, payload=payload or {})
        self.event_logger.log(event)

        if not self.hooks:
            return

        for hook in self.hooks:
            result = hook(event)
            if inspect.isawaitable(result):
                await result


__all__ = [
    "AgentBudget",
    "AgentLoopHarness",
    "AgentRunContext",
    "BudgetViolation",
    "ConstraintSet",
    "ConstraintViolation",
    "ContinuousImprovement",
    "FeedbackLoop",
    "HarnessEvent",
    "HarnessEventLogger",
    "HarnessHook",
    "ImprovementRecord",
    "InMemoryImprovementStore",
    "WorkflowController",
    "WorkflowDecision",
]
