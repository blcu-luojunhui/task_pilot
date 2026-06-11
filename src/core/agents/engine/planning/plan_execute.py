"""Plan-Execute 策略 — 先产出计划再逐步执行，减少任务漂移"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from .strategy import DecisionStrategy, StepOutput, StrategyContext

if TYPE_CHECKING:
    from ...state import AgentLoopState


class PlanExecuteStrategy:
    """Plan-and-Execute 策略。

    on_run_start：调用 LLM 生成初始计划（写入 state.plan）
    run_step：取下一个 pending 步骤设为 in_progress 并注入 prompt 执行。
    """

    name: str = "plan_execute"

    async def on_run_start(self, state: "AgentLoopState", ctx: StrategyContext) -> None:
        plan_text = await self._generate_plan(state, ctx)
        if plan_text:
            self._build_plan_steps(state, plan_text)

    async def run_step(self, state: "AgentLoopState", ctx: StrategyContext) -> StepOutput:
        from .react import ReActStrategy
        from ...engine.types import PlanStepStatus

        plan = getattr(state, "plan", []) or []
        # 推进当前 in_progress → done（上一轮执行的结果）
        for ps in plan:
            if ps.status == PlanStepStatus.IN_PROGRESS:
                ps.status = PlanStepStatus.DONE

        # 取第一个 pending → in_progress
        pending = [s for s in plan if s.status == PlanStepStatus.PENDING]
        if pending:
            pending[0].status = PlanStepStatus.IN_PROGRESS
            # 将当前 plan step 注入为子目标
            original_goal = state.goal
            state.goal = f"[Step {pending[0].id}] {pending[0].goal}"

        react = ReActStrategy()
        output = await react.run_step(state, ctx)

        # 恢复原始 goal
        if pending:
            state.goal = original_goal

        return output

    async def on_step_end(self, state: "AgentLoopState", ctx: StrategyContext, output: StepOutput) -> None:
        pass

    # ── helpers ──

    async def _generate_plan(self, state: "AgentLoopState", ctx: StrategyContext) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a planning assistant. Given a goal, produce a step-by-step plan. "
                    "Output each step on a new line starting with '- '. Be concise."
                ),
            },
            {"role": "user", "content": f"Goal: {state.goal}\n\nBreak this down into numbered steps:"},
        ]
        try:
            result = await ctx.thinker.planner(messages, step=0)
            return result.get("content", "") if result else ""
        except Exception:
            return ""

    @staticmethod
    def _build_plan_steps(state: "AgentLoopState", plan_text: str) -> None:
        from ...engine.types import PlanStep, PlanStepStatus

        lines = [
            line.strip("- ").strip()
            for line in plan_text.split("\n")
            if line.strip().startswith("-")
        ]
        if not lines:
            return

        state.plan = [
            PlanStep(
                id=f"step_{i}_{uuid.uuid4().hex[:6]}",
                goal=line,
                status=PlanStepStatus.IN_PROGRESS if i == 0 else PlanStepStatus.PENDING,
            )
            for i, line in enumerate(lines)
        ]
