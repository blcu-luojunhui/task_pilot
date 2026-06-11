"""Reflexion 策略 — ReAct + 失败后反思，提升自动恢复率"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .strategy import DecisionStrategy, StepOutput, StrategyContext

if TYPE_CHECKING:
    from ..state import AgentLoopState


class ReflexionStrategy:
    """Reflexion 策略。

    在 ReAct 基础上，连续工具失败时触发反思（由 OPT-3 的 ReflectionProvider 完成）。
    本策略提供一个 on_step_end 钩子，配合 ReflectionProvider 注入反思内容。
    """

    name: str = "reflexion"

    async def on_run_start(self, state: "AgentLoopState", ctx: StrategyContext) -> None:
        pass

    async def run_step(self, state: "AgentLoopState", ctx: StrategyContext) -> StepOutput:
        from .react import ReActStrategy

        react = ReActStrategy()
        return await react.run_step(state, ctx)

    async def on_step_end(self, state: "AgentLoopState", ctx: StrategyContext, output: StepOutput) -> None:
        # OPT-3 的 ReflectionProvider 会通过 FeedbackLoop 注入反思内容
        pass
