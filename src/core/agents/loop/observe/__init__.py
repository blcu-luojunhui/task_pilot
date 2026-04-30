"""
Observe stage for the agent loop.

Observe writes Think/Act results back to state and decides termination.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from src.core.agents.loop.messages import get_tool_calls
from src.core.agents.loop.state import AgentLoopState, StopReason


@dataclass
class Observe:
    """Observation stage of the agent loop."""

    abort_on_tool_error: bool = True

    def run(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> None:
        state.add_assistant_message(assistant_message)

        tool_calls = get_tool_calls(assistant_message)
        if not tool_calls:
            state.final_answer = assistant_message.get("content")
            state.stop_reason = StopReason.MODEL_FINAL
            return

        state.add_tool_results(tool_results)

        if self.abort_on_tool_error and any(r.get("is_error") for r in tool_results):
            state.stop_reason = StopReason.TOOL_ERROR_ABORT


__all__ = ["Observe"]
