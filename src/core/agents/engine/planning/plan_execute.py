"""Plan-Execute 策略 — 先产出计划再逐步执行，减少任务漂移"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from .strategy import StepOutput, StrategyContext

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
        state.metadata["planning"] = {
            "strategy": self.name,
            "status": "created" if state.plan else "fallback_to_react",
            "step_count": len(state.plan),
        }

    async def run_step(self, state: "AgentLoopState", ctx: StrategyContext) -> StepOutput:
        from .react import ReActStrategy
        from ...engine.types import PlanStepStatus
        from ...state import StopReason

        plan = getattr(state, "plan", []) or []
        react = ReActStrategy()
        if not plan:
            return await react.run_step(state, ctx)

        current = next(
            (step for step in plan if step.status == PlanStepStatus.IN_PROGRESS),
            None,
        )
        if current is None:
            current = next(
                (step for step in plan if step.status == PlanStepStatus.PENDING),
                None,
            )
            if current is None:
                return await react.run_step(state, ctx)
            current.status = PlanStepStatus.IN_PROGRESS

        original_goal = state.goal
        state.goal = f"[Plan step {current.id}] {current.goal}"
        try:
            output = await react.run_step(state, ctx)
        finally:
            state.goal = original_goal

        if state.stop_reason == StopReason.MODEL_FINAL:
            current.status = PlanStepStatus.DONE
            current.result = state.final_answer
            if any(step.status == PlanStepStatus.PENDING for step in plan):
                # 当前子目标完成不等于整个计划完成。清除 ReAct 的终止标记，
                # 让下一轮继续处理后续子目标。
                state.stop_reason = None
                state.final_answer = None
        elif state.stop_reason in {
            StopReason.LLM_ERROR_ABORT,
            StopReason.TOOL_ERROR_ABORT,
            StopReason.ERROR,
            StopReason.CONSTRAINT_VIOLATION,
        }:
            current.status = PlanStepStatus.FAILED
            current.result = self._failure_result(output)

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
            usage = result.get("_usage") if result else None
            if usage:
                for key in ("prompt", "completion", "total"):
                    state.token_usage[key] = (
                        state.token_usage.get(key, 0) + usage.get(key, 0)
                    )
            return result.get("content", "") if result else ""
        except Exception:
            return ""

    @staticmethod
    def _build_plan_steps(state: "AgentLoopState", plan_text: str) -> None:
        from ...engine.types import PlanStep, PlanStepStatus

        lines = []
        for raw_line in plan_text.splitlines():
            match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$", raw_line)
            if match:
                lines.append(match.group(1))
        if not lines:
            return

        state.plan = [
            PlanStep(
                id=f"step_{i}_{uuid.uuid4().hex[:6]}",
                goal=line,
                status=PlanStepStatus.PENDING,
            )
            for i, line in enumerate(lines)
        ]

    @staticmethod
    def _failure_result(output: StepOutput) -> str:
        errors = [
            str(result.get("content", ""))
            for result in output.tool_results
            if str(result.get("content", "")).startswith("Error:")
        ]
        if errors:
            return "\n".join(errors)
        return "Plan step terminated before completion"
