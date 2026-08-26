"""
Harness layer for the agent loop.

The harness owns lifecycle concerns: run context, step boundaries, events,
hooks, cancellation checks, and final result building. Think/Act/Observe stay
focused on their own stage logic.
"""

import inspect
import logging
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

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
from src.core.agents.engine.planning.strategy import (
    DecisionStrategy,
    StrategyContext,
)
from src.core.agents.engine.planning.react import ReActStrategy
from src.core.agents.runtime.harness.approval import ApprovalDecision, ApprovalPolicy
from src.core.agents.runtime.harness.reconciliation import ReconciliationDecision
from src.core.agents.state.protocol import tool_result_message
from src.core.agents.capabilities.skills.security import redact_sensitive_data
from src.core.agents.execution import ToolExecutionLedgerError

logger = logging.getLogger(__name__)

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
    event_bus: Optional[Any] = None  # 共享 TraceEventBus，用于 chat.* 事件


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
    strategy: Optional[DecisionStrategy] = None
    event_bus: Optional[Any] = None  # 共享 TraceEventBus
    approval_policy: Optional[ApprovalPolicy] = None

    def __post_init__(self) -> None:
        if self.workflow is None:
            self.workflow = WorkflowController(
                budget=self.budget,
                is_cancelled=self.is_cancelled,
                constraints=self.constraints,
            )
        self._current_state: Optional[AgentLoopState] = None
        if self.thinker.publish_event is None:
            self.thinker.publish_event = self._emit_thinker_event
        # 注入 event_bus 到 Think/Act（若它们还没被外部设过）
        if self.event_bus is not None:
            if self.thinker.event_bus is None:
                self.thinker.event_bus = self.event_bus
            if self.actor.event_bus is None:
                self.actor.event_bus = self.event_bus
        if self.strategy is None:
            self.strategy = ReActStrategy()
        self._strategy_ctx = StrategyContext(
            thinker=self.thinker,
            actor=self.actor,
            observer=self.observer,
            approval_policy=self.approval_policy,
        )

    async def run(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        initial_state: Optional[AgentLoopState] = None,
        approval_decision: Optional[ApprovalDecision] = None,
        reconciliation_decision: Optional[ReconciliationDecision] = None,
    ) -> AgentLoopResult:
        run_metadata = dict(metadata or {})
        run_trace_id = (
            trace_id
            or (initial_state.trace_id if initial_state else None)
            or run_metadata.get("trace_id")
            or generate_agent_trace_id()
        )
        run_metadata["trace_id"] = run_trace_id

        state = initial_state or AgentLoopState(
            goal=goal,
            messages=list(messages or []),
            max_steps=self.budget.max_steps,
            trace_id=run_trace_id,
            metadata=dict(run_metadata),
        )
        state.trace_id = run_trace_id
        state.metadata.update(run_metadata)
        context = AgentRunContext(
            state=state,
            started_at=time.monotonic(),
            metadata=run_metadata,
        )
        self._current_state = state

        try:
            event_name = "run_resumed" if initial_state else "run_start"
            await self._emit(event_name, state, {"metadata": context.metadata, "goal": state.goal})

            # 同步 lifecycle 初始状态
            if self.lifecycle:
                self.lifecycle.current_loop_state = state
                if self.lifecycle.state == AgentState.IDLE:
                    self.lifecycle.transition_to(AgentState.RUNNING, reason="harness start")
                state.lifecycle_state = self.lifecycle.state

            assert self.strategy is not None
            if initial_state is None:
                # 策略初始化钩子（如 PlanExecute 生成 plan）
                await self.strategy.on_run_start(state, self._strategy_ctx)
            elif state.pending_approval:
                await self._resume_pending_approval(state, approval_decision)
            elif state.pending_reconciliation:
                await self._resume_pending_reconciliation(state, reconciliation_decision)

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

                # ── 委托给策略执行单步 Think → Act → Observe ──
                step_output = await self.strategy.run_step(state, self._strategy_ctx)
                assistant_message = step_output.assistant_message
                tool_results = step_output.tool_results

                if step_output.stop_reason_override:
                    state.stop_reason = step_output.stop_reason_override
                    if state.stop_reason == StopReason.APPROVAL_REQUIRED:
                        await self._emit(
                            "approval_required",
                            state,
                            dict(state.pending_approval or {}),
                        )
                    elif state.stop_reason == StopReason.EXECUTION_IN_DOUBT:
                        await self._emit(
                            "reconciliation_required",
                            state,
                            self._public_reconciliation(state),
                        )
                if assistant_message is not None and not state.is_terminated():
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

                if (
                    assistant_message is not None
                    and not state.pending_approval
                    and not state.pending_reconciliation
                ):
                    # 构建结构化 Step 记录（并行工具调用各自一个 Step）
                    step_records = self._build_step_records(state, assistant_message, tool_results)
                    state.steps.extend(step_records)

                    # 策略步后钩子（如 Reflexion）
                    await self.strategy.on_step_end(state, self._strategy_ctx, step_output)

                await self._emit(
                    "step_end",
                    state,
                    {
                        "assistant_message": assistant_message,
                        "tool_results": tool_results,
                    },
                )

                if state.is_terminated() or assistant_message is None:
                    break

        except Exception as e:
            logger.exception(f"Agent loop crashed at step {state.step}: {e}")
            if not state.stop_reason:
                state.stop_reason = StopReason.ERROR
            if self.lifecycle:
                state.lifecycle_state = self.lifecycle.state
            await self._emit("run_error", state, {"error": str(e)})
            # 发布 chat.turn_error 给前端
            self._publish_chat_event(state, "turn_error", {"error": str(e)})

        if self.lifecycle:
            self.lifecycle.current_loop_state = state
            state.lifecycle_state = self.lifecycle.state
        result = self._build_result(context)
        improvement_record = None
        if state.stop_reason not in {
            StopReason.APPROVAL_REQUIRED,
            StopReason.EXECUTION_IN_DOUBT,
        }:
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
        if state.stop_reason in {
            StopReason.APPROVAL_REQUIRED,
            StopReason.EXECUTION_IN_DOUBT,
        }:
            pause_reason = (
                "approval" if state.stop_reason == StopReason.APPROVAL_REQUIRED
                else "reconciliation"
            )
            await self._emit(
                "run_paused",
                state,
                {"result": result, "pause_reason": pause_reason},
            )
            self._publish_chat_event(
                state,
                "turn_paused",
                {
                    "pending_approval": result.pending_approval,
                    "pending_reconciliation": result.pending_reconciliation,
                    "pause_reason": pause_reason,
                },
            )
        else:
            await self._emit("run_end", state, {"result": result})
            # 发布 chat.turn_end 给前端
            self._publish_chat_event(state, "turn_end", {
                "content": result.final_answer or "",
                "token_usage": dict(state.token_usage),
            })
        return result

    async def _resume_pending_approval(
        self,
        state: AgentLoopState,
        decision: Optional[ApprovalDecision],
    ) -> None:
        pending = dict(state.pending_approval or {})
        request = pending.get("request") or {}
        assistant_message = pending.get("assistant_message")
        if decision is None:
            raise ValueError("approval_decision is required to resume this run")
        if decision.request_id != request.get("request_id"):
            raise ValueError("approval_decision.request_id does not match pending approval")
        if not isinstance(assistant_message, dict):
            raise ValueError("pending approval has no assistant message")

        state.stop_reason = None
        state.pending_approval = None
        history = state.metadata.setdefault("approval_history", [])
        history.append(decision.to_dict())
        await self._emit(
            "approval_resolved",
            state,
            {"request": request, "decision": decision.to_dict()},
        )

        tool_calls = get_tool_calls(assistant_message)
        if decision.decision == "approve":
            tool_results = await self.actor.run(state, tool_calls)
        else:
            reason = redact_sensitive_data(decision.reason or "rejected by reviewer")
            tool_results = [
                tool_result_message(
                    call.id,
                    f"Error: Tool call rejected by human reviewer: {reason}",
                )
                for call in tool_calls
            ]

        if state.pending_reconciliation:
            state.pending_reconciliation["assistant_message"] = assistant_message
            target_id = state.pending_reconciliation["tool_call_id"]
            target_index = next(
                (
                    index
                    for index, result in enumerate(tool_results)
                    if result.get("tool_call_id") == target_id
                ),
                len(tool_results),
            )
            state.pending_reconciliation["tool_results_before"] = tool_results[:target_index]
            await self._emit(
                "reconciliation_required",
                state,
                self._public_reconciliation(state),
            )
            return

        self.observer.run(state, assistant_message, tool_results)
        state.steps.extend(self._build_step_records(state, assistant_message, tool_results))
        await self._emit(
            "step_end",
            state,
            {
                "assistant_message": assistant_message,
                "tool_results": tool_results,
                "resumed_from_approval": True,
            },
        )

    @staticmethod
    def _public_reconciliation(state: AgentLoopState) -> Dict[str, Any]:
        pending = dict(state.pending_reconciliation or {})
        pending.pop("assistant_message", None)
        pending.pop("tool_results_before", None)
        return pending

    async def _resume_pending_reconciliation(
        self,
        state: AgentLoopState,
        decision: Optional[ReconciliationDecision],
    ) -> None:
        pending = dict(state.pending_reconciliation or {})
        assistant_message = pending.get("assistant_message")
        call_id = pending.get("tool_call_id")
        if decision is None:
            raise ValueError("reconciliation_decision is required to resume this run")
        if decision.tool_call_id != call_id:
            raise ValueError(
                "reconciliation_decision.tool_call_id does not match pending reconciliation"
            )
        if not isinstance(assistant_message, dict):
            raise ValueError("pending reconciliation has no assistant message")

        tool_calls = get_tool_calls(assistant_message)
        target_index = next(
            (index for index, call in enumerate(tool_calls) if call.id == call_id),
            None,
        )
        if target_index is None:
            raise ValueError("pending reconciliation tool call is missing")

        ledger = self.actor.execution_ledger
        if ledger is None:
            await self._emit(
                "reconciliation_resolution_failed",
                state,
                {"error": "durable execution ledger is unavailable"},
            )
            return
        try:
            await ledger.resolve(
                state.trace_id,
                decision.tool_call_id,
                decision=decision.decision,
                result_content=(
                    decision.tool_message_content()
                    if decision.decision == "completed"
                    else None
                ),
                error_message=(
                    decision.to_audit_dict().get("reason")
                    or "human reconciliation marked execution as failed"
                ),
            )
        except ToolExecutionLedgerError as exc:
            await self._emit(
                "reconciliation_resolution_failed",
                state,
                {"error": str(exc)},
            )
            return

        state.stop_reason = None
        state.pending_reconciliation = None
        history = state.metadata.setdefault("reconciliation_history", [])
        history.append(decision.to_audit_dict())
        await self._emit(
            "reconciliation_resolved",
            state,
            {
                "pending": self._public_reconciliation_from_mapping(pending),
                "decision": decision.to_audit_dict(),
            },
        )

        tool_results = list(pending.get("tool_results_before") or [])
        tool_results.append(
            tool_result_message(decision.tool_call_id, decision.tool_message_content())
        )
        remaining_calls = tool_calls[target_index + 1 :]
        if decision.decision == "completed" and remaining_calls:
            resumed_results = await self.actor.run(state, remaining_calls)
            tool_results.extend(resumed_results)
            if state.pending_reconciliation:
                state.pending_reconciliation["assistant_message"] = assistant_message
                state.pending_reconciliation["tool_results_before"] = list(tool_results[:-1])
        elif remaining_calls:
            reason = "not executed because an earlier side effect was reconciled as failed"
            tool_results.extend(
                tool_result_message(call.id, f"Error: {reason}")
                for call in remaining_calls
            )

        if not state.pending_reconciliation:
            self.observer.run(state, assistant_message, tool_results)
            state.steps.extend(self._build_step_records(state, assistant_message, tool_results))
        await self._emit(
            "step_end",
            state,
            {
                "assistant_message": assistant_message,
                "tool_results": tool_results,
                "resumed_from_reconciliation": True,
            },
        )
        if state.pending_reconciliation:
            await self._emit(
                "reconciliation_required",
                state,
                self._public_reconciliation(state),
            )

    @staticmethod
    def _public_reconciliation_from_mapping(pending: Dict[str, Any]) -> Dict[str, Any]:
        public = dict(pending)
        public.pop("assistant_message", None)
        public.pop("tool_results_before", None)
        return public

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
        result_metadata = dict(context.metadata)
        if state.metadata.get("approval_history"):
            result_metadata["approval_history"] = list(state.metadata["approval_history"])
        if state.metadata.get("reconciliation_history"):
            result_metadata["reconciliation_history"] = list(
                state.metadata["reconciliation_history"]
            )
        if state.metadata.get("planning"):
            result_metadata["planning"] = dict(state.metadata["planning"])
        if state.plan:
            result_metadata["plan"] = [
                {
                    "id": plan_step.id,
                    "goal": plan_step.goal,
                    "status": plan_step.status.value,
                    "result": plan_step.result,
                }
                for plan_step in state.plan
            ]
        return AgentLoopResult(
            trace_id=state.trace_id,
            success=state.stop_reason == StopReason.MODEL_FINAL,
            final_answer=state.final_answer,
            stop_reason=state.stop_reason,
            total_steps=state.step,
            tool_calls_count=len(tool_call_steps),
            duration_seconds=time.monotonic() - context.started_at,
            token_usage=dict(state.token_usage),
            metadata=result_metadata,
            pending_approval=(
                dict(state.pending_approval["request"])
                if state.pending_approval and state.pending_approval.get("request")
                else None
            ),
            pending_reconciliation=(
                self._public_reconciliation(state)
                if state.pending_reconciliation
                else None
            ),
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

    def _publish_chat_event(self, state: AgentLoopState, event_type: str, data: Dict[str, Any]) -> None:
        """向共享 event_bus 发布 chat.* 事件（前端消费）。"""
        _bus = self.event_bus
        if _bus is None:
            return
        try:
            _bus.publish(
                trace_id=state.trace_id,
                event_type=event_type,
                data=data,
                source="agent",
                step=state.step,
            )
        except Exception:
            pass

    async def _emit_thinker_event(
        self,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        step: Optional[int] = None,
    ) -> None:
        """Think.publish_event 适配器：将 Think 的调用签转成 _emit(state, payload)。"""
        if self._current_state is None:
            return
        await self._emit(name, self._current_state, payload)

    async def _emit(
        self,
        name: str,
        state: AgentLoopState,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = HarnessEvent(name=name, state=state, payload=payload or {})
        self.event_logger.log(event)

        if self.event_bus is not None:
            try:
                self.event_bus.publish(
                    trace_id=state.trace_id,
                    event_type=name,
                    data=self._to_event_data(event.payload),
                    source="harness",
                    step=state.step,
                )
            except Exception:
                logger.warning("Failed to publish harness event %s", name, exc_info=True)

        for hook in self.hooks:
            result = hook(event)
            if inspect.isawaitable(result):
                await result

    @classmethod
    def _to_event_data(cls, value: Any) -> Any:
        """Convert harness payloads into JSON-safe event data."""
        if is_dataclass(value) and not isinstance(value, type):
            return cls._to_event_data(asdict(value))
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            converted = {str(key): cls._to_event_data(item) for key, item in value.items()}
            return redact_sensitive_data(converted)
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._to_event_data(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)


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
