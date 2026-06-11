"""Artifact tools — read_artifact 按需回读卸载的大结果"""

from src.core.agents.capabilities.skills import skill, SkillContext


@skill(
    name="read_artifact",
    description=(
        "Read a previously offloaded large tool result from the artifact store. "
        "Use this when you need the full content of a result that was truncated."
    ),
    dependencies=[],
    risk_level="read",
    parameters={
        "id": {
            "type": "string",
            "description": "Artifact ID (from the artifact:// URL in the truncated result)",
            "required": True,
        },
        "offset": {
            "type": "integer",
            "description": "Character offset to start reading from (default 0)",
            "required": False,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum characters to read (default 2000)",
            "required": False,
        },
    },
)
async def read_artifact(ctx: SkillContext, id: str, offset: int = 0, limit: int = 2000) -> str:
    """读取 artifact 内容。需要 state 中有 artifact_store。"""
    store = getattr(ctx, "_artifact_store", None)
    if store is None:
        return "Error: artifact store not available (offload not enabled)"

    state = getattr(ctx, "_state", None)
    trace_id = state.trace_id if state else "unknown"

    return await store.get(artifact_id=id, trace_id=trace_id, offset=offset, limit=limit)
