"""ReflectionProvider — 连续失败后生成针对性反思，注入下一轮 Think"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.core.agents.state import AgentLoopState

logger = logging.getLogger(__name__)

AssistantPlanner = Callable[..., Any]


@dataclass
class ReflectionProvider:
    """连续工具失败时调用 LLM 生成反思文本，注入下一轮对话。

    通过 FeedbackLoop 机制工作：ReflectionProvider 是一个标准 FeedbackProvider，
    在 harness 的 feedback 收集阶段被调用。
    """

    planner: AssistantPlanner
    trigger_errors: int = 2
    max_reflection_tokens: int = 300
    enabled: bool = True

    async def __call__(
        self,
        state: AgentLoopState,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        if state.consecutive_tool_errors < self.trigger_errors:
            return None

        prompt = self._build_reflection_prompt(state, payload)
        try:
            resp = await self.planner(
                [{"role": "user", "content": prompt}],
                step=state.step,
            )
            if not resp:
                return None
            text = (resp.get("content") or "").strip()
        except Exception:
            logger.exception("ReflectionProvider: planner call failed")
            return None

        if not text:
            return None

        logger.debug(
            "[%s] Reflection generated (%d chars): %s",
            state.trace_id,
            len(text),
            text[:200],
        )
        return {
            "role": "user",
            "name": "reflection",
            "content": f"[Reflection on recent errors]\n{text}",
        }

    def _build_reflection_prompt(self, state: AgentLoopState, payload: Dict[str, Any]) -> str:
        recent_errors = []
        tool_results = payload.get("tool_results", [])
        for r in tool_results:
            content = str(r.get("content", ""))
            if content.startswith("Error:"):
                recent_errors.append(content)

        error_list = "\n".join(f"- {e}" for e in recent_errors) if recent_errors else "(unknown)"
        return (
            f"You are analyzing recent tool execution failures to suggest a better approach.\n\n"
            f"Goal: {state.goal}\n\n"
            f"Recent tool errors ({state.consecutive_tool_errors} consecutive):\n{error_list}\n\n"
            f"Analyze WHY these failures occurred and suggest a CONCRETE alternative strategy "
            f"(a different tool, different parameters, or how to proceed without the failing tool). "
            f"Be brief — max {self.max_reflection_tokens} tokens."
        )
