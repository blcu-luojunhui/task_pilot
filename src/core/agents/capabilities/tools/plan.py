"""Plan tools — update_plan 内置工具，允许 Agent 修订结构化计划"""

from typing import Any, Dict, List

from src.core.agents.capabilities.skills import skill, SkillContext


@skill(
    name="update_plan",
    domain="plan",
    description=(
        "Update the agent's structured plan (todo list). "
        "Use this to mark steps as done/failed/skipped or add new steps. "
        "Each step must have: goal (string), status (one of: pending, in_progress, done, failed, skipped)."
    ),
    dependencies=[],
    risk_level="read",
    parameters={
        "steps": {
            "type": "array",
            "description": "List of plan steps to update or add. Each step: {goal: str, status: str}.",
            "items": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Step description"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "done", "failed", "skipped"],
                        "description": "Step status",
                    },
                },
                "required": ["goal", "status"],
            },
        },
    },
)
async def update_plan(ctx: SkillContext, steps: List[Dict[str, Any]]) -> str:
    """更新结构化计划。通过 ctx._state.plan 写入 AgentLoopState。"""
    from src.core.agents.engine.types import PlanStep, PlanStepStatus

    state = getattr(ctx, "_state", None)
    if state is None:
        return "Error: plan state not available (no current agent state in context)"

    if not hasattr(state, "plan"):
        return "Error: plan not supported in current agent state"

    updated = 0
    added = 0
    for s in steps:
        goal = s.get("goal", "")
        status_str = s.get("status", "pending")
        try:
            status = PlanStepStatus(status_str)
        except ValueError:
            return f"Error: invalid status '{status_str}'. Valid: pending, in_progress, done, failed, skipped"

        # 查找已有步骤（按 goal 匹配）并更新
        found = False
        for ps in state.plan:
            if ps.goal == goal:
                ps.status = status
                if s.get("result"):
                    ps.result = s["result"]
                found = True
                updated += 1
                break

        if not found:
            import uuid
            step_id = f"plan_{uuid.uuid4().hex[:8]}"
            state.plan.append(PlanStep(id=step_id, goal=goal, status=status, result=s.get("result")))
            added += 1

    # 发事件
    try:
        thinker = getattr(ctx, "_thinker", None)
        if thinker and thinker.publish_event:
            import inspect
            result = thinker.publish_event("plan_updated", {"plan": [
                {"id": ps.id, "goal": ps.goal, "status": ps.status.value, "result": ps.result}
                for ps in state.plan
            ]}, step=state.step)
            if inspect.isawaitable(result):
                await result
    except Exception:
        pass

    return f"Plan updated: {updated} step(s) modified, {added} step(s) added. Total steps: {len(state.plan)}"
