"""Handoff 工具 (OPT-10) — 把控制权显式移交给另一个专长 agent"""

from typing import Optional

from src.core.agents.capabilities.skills import skill, SkillContext


_MAX_HANDOFF_DEPTH = 3  # 防成环


@skill(
    name="handoff_to",
    description=(
        "Transfer control to another specialized agent. "
        "Use this when another agent is better suited for the current task. "
        "The current agent will stop and the target agent will continue."
    ),
    dependencies=[],
    risk_level="write",
    parameters={
        "target_agent_id": {
            "type": "string",
            "description": "ID of the agent to hand off to",
            "required": True,
        },
        "reason": {
            "type": "string",
            "description": "Why this handoff is needed",
            "required": False,
        },
    },
)
async def handoff_to(
    ctx: SkillContext,
    target_agent_id: str,
    reason: str = "",
) -> str:
    """执行 handoff：标记当前 run 以 handoff 结束"""
    state = getattr(ctx, "_state", None)
    if state is None:
        return "Error: no agent state available for handoff"

    # 防环：记录 handoff 链
    chain = getattr(state, "metadata", {}).get("handoff_chain", [])
    if target_agent_id in chain:
        return f"Error: handoff cycle detected — already visited {target_agent_id}"
    if len(chain) >= _MAX_HANDOFF_DEPTH:
        return f"Error: handoff depth limit ({_MAX_HANDOFF_DEPTH}) exceeded"

    new_chain = list(chain) + [target_agent_id]
    if not hasattr(state, "metadata"):
        state.metadata = {}
    state.metadata["handoff_chain"] = new_chain
    state.metadata["handoff_target"] = target_agent_id
    state.metadata["handoff_reason"] = reason

    # 设置 stop_reason 为 HANDOFF，harness 检测后终止
    from src.core.agents.state import StopReason  # noqa

    state.stop_reason = StopReason.USER_CANCELLED  # 复用取消机制终止当前 run

    return (
        f"Handoff to agent '{target_agent_id}' initiated"
        + (f" (reason: {reason})" if reason else "")
    )


__all__ = ["handoff_to"]
