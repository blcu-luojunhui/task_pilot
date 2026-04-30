"""
Think stage for the agent loop.

Think only asks the planner for the next assistant message.
"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.agents.loop.state import AgentLoopState, StopReason

logger = logging.getLogger(__name__)

AssistantPlanner = Callable[[List[Dict[str, Any]], int], Awaitable[Dict[str, Any]]]


@dataclass
class Think:
    """Thinking stage of the agent loop."""

    planner: AssistantPlanner

    async def run(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        try:
            return await self.planner(state.messages, state.step)
        except Exception:
            logger.exception("Agent planner failed at step %s", state.step)
            state.stop_reason = StopReason.LLM_ERROR_ABORT
            return None


__all__ = ["AssistantPlanner", "Think"]
