"""ReAct 策略 — 等价于现有 Think → Act → Observe 行为，零回归"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .strategy import DecisionStrategy, StepOutput, StrategyContext

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
            tool_results = await ctx.actor.run(state, tool_calls)

        # 3. Observe
        ctx.observer.run(state, assistant_message, tool_results)

        return StepOutput(assistant_message=assistant_message, tool_results=tool_results)

    async def on_step_end(self, state: "AgentLoopState", ctx: StrategyContext, output: StepOutput) -> None:
        pass
