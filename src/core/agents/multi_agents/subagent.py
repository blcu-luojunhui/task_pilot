"""子代理隔离 (OPT-9) — spawn_subagent 在独立上下文运行子任务"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.agent import Agent
    from ..state import AgentLoopState
    from ..capabilities.skills import SkillContext

logger = logging.getLogger(__name__)

_MAX_SPAWN_DEPTH = 2  # 防递归 spawn 失控


class SubAgentSpawner:
    """工厂持有父 agent 的 provider/config 模板，用于 spawn 子代理。

    通过作为 Skill handler 使用：
        agent.skill(name="spawn_subagent", ...)(spawner.spawn)
    """

    def __init__(
        self,
        parent_agent: "Agent",
        max_depth: int = _MAX_SPAWN_DEPTH,
    ):
        self._parent = parent_agent
        self._max_depth = max_depth
        self._depth: Dict[str, int] = {}

    async def spawn(
        self,
        ctx: "SkillContext",
        goal: str,
        tool_areas: Optional[List[str]] = None,
        max_steps: int = 5,
    ) -> str:
        """spawn_subagent(goal, tool_areas?, max_steps?) -> 子代理最终答案"""
        parent_state: "Optional[AgentLoopState]" = getattr(ctx, "_state", None)
        parent_trace_id = parent_state.trace_id if parent_state else "unknown"
        depth_key = parent_trace_id

        current_depth = self._depth.get(depth_key, 0)
        if current_depth >= self._max_depth:
            return f"Error: spawn depth limit ({self._max_depth}) exceeded — cannot spawn sub-agent"

        self._depth[depth_key] = current_depth + 1
        sub_trace_id = f"{parent_trace_id}-sub-{current_depth + 1}"

        try:
            # 创建独立 Agent（复用父 provider/config）
            from ..engine.agent import Agent

            sub_config = self._parent.config
            sub_agent = Agent.create(
                llm_api_key=sub_config.llm_api_key,
                llm_provider=sub_config.llm_provider,
                llm_model=sub_config.llm_model,
                llm_base_url=sub_config.llm_base_url,
                max_steps=min(max_steps, sub_config.max_steps),
                tool_areas=tool_areas or sub_config.tool_areas,
                strategy=sub_config.strategy,
            )

            # 子代理的取消回调：跟随父 lifecycle
            parent_lifecycle = self._parent._lifecycle
            sub_config_wrapper = self._parent.config
            sub_agent._runner.is_cancelled = lambda: parent_lifecycle.is_stop_requested()

            result = await sub_agent.run(
                goal=goal,
                messages=None,
                metadata={"parent_trace_id": parent_trace_id, "depth": current_depth + 1},
                trace_id=sub_trace_id,
            )

            if result.success and result.final_answer:
                logger.debug("Sub-agent %s completed: %s", sub_trace_id, result.final_answer[:100])
                return f"[Sub-agent result]\n{result.final_answer}"
            return f"[Sub-agent failed: {result.stop_reason.value if result.stop_reason else 'unknown'}]"
        except Exception as e:
            logger.exception("Sub-agent %s crashed", sub_trace_id)
            return f"Error: sub-agent failed: {e}"
        finally:
            self._depth[depth_key] = max(0, self._depth.get(depth_key, 1) - 1)


__all__ = ["SubAgentSpawner"]
