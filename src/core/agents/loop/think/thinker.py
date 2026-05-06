"""Think stage implementation"""

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.agents.foundation.context import ContextWindowManager
from src.core.agents.foundation.state import AgentLoopState, StopReason
from src.infra.streaming.agents import set_stream_context, clear_stream_context
from .prompt_assembler import PromptAssembler

logger = logging.getLogger(__name__)

AssistantPlanner = Callable[[List[Dict[str, Any]], int], Awaitable[Dict[str, Any]]]


@dataclass
class Think:
    """Thinking stage of the agent loop."""

    planner: AssistantPlanner
    context_manager: Optional[ContextWindowManager] = None
    prompt_assembler: Optional[PromptAssembler] = None
    stream_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None

    async def run(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        messages = list(state.messages)
        if self.prompt_assembler:
            messages = [self.prompt_assembler.assemble(state)] + messages
        if self.context_manager:
            messages = self.context_manager.compact_if_needed(messages)

        set_stream_context(
            trace_id=state.trace_id,
            step=state.step,
            sink=self.stream_sink,
        )
        try:
            return await self.planner(messages, state.step)
        except Exception:
            logger.exception("Agent planner failed at step %s", state.step)
            state.stop_reason = StopReason.LLM_ERROR_ABORT
            return None
        finally:
            clear_stream_context()
