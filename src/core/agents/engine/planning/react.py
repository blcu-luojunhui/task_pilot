"""ReAct 策略 — 等价于现有 Think → Act → Observe 行为，零回归"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .strategy import StepOutput, StrategyContext

if TYPE_CHECKING:
    from ..state import AgentLoopState


class ReActStrategy:
    """ReAct (Reasoning + Acting) 策略，完全等价改造前的默认行为。

    run_step = Think → Act → Observe，不做规划或反思。
    """

    name: str = "react"

    async def on_run_start(self, state: "AgentLoopState", ctx: StrategyContext) -> None:
        pass

    async def run_step(self, state: "AgentLoopState", ctx: StrategyContext) -> StepOutput:
        # 1. Think
        assistant_message = await ctx.thinker.run(state)

        if state.is_terminated() or assistant_message is None:
            return StepOutput(assistant_message=assistant_message, tool_results=[])

        # 2. Act — 从 assistant_message 提取 tool calls
        from ...state.protocol import get_tool_calls

        tool_calls = get_tool_calls(assistant_message)
        tool_results: list = []
        if tool_calls:
            if ctx.approval_policy:
                request = ctx.approval_policy.create_request(
                    tool_calls,
                    ctx.actor.registry,
                    trace_id=state.trace_id,
                    step=state.step,
                )
                if request:
                    from ...state import StopReason

                    state.pending_approval = {
                        "request": request.to_dict(),
                        "assistant_message": assistant_message,
                    }
                    return StepOutput(
                        assistant_message=assistant_message,
                        tool_results=[],
                        stop_reason_override=StopReason.APPROVAL_REQUIRED,
                    )
            tool_results = await ctx.actor.run(state, tool_calls)
            if state.pending_reconciliation:
                from ...state import StopReason

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
                return StepOutput(
                    assistant_message=assistant_message,
                    tool_results=tool_results,
                    stop_reason_override=StopReason.EXECUTION_IN_DOUBT,
                )

        # 3. Observe
        ctx.observer.run(state, assistant_message, tool_results)

        return StepOutput(assistant_message=assistant_message, tool_results=tool_results)

    async def on_step_end(self, state: "AgentLoopState", ctx: StrategyContext, output: StepOutput) -> None:
        pass
