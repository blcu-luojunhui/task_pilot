"""Observe stage implementation"""

from dataclasses import dataclass
from typing import Any, Dict, List

from src.core.agents.foundation.protocol import get_tool_calls
from src.core.agents.foundation.state import AgentLoopState, StopReason


@dataclass
class Observe:
    """Observation stage of the agent loop."""

    abort_on_tool_error: bool = False
    max_consecutive_errors: int = 3

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

        has_errors = any(r.get("is_error") for r in tool_results)
        if has_errors:
            state.consecutive_tool_errors += 1
        else:
            state.consecutive_tool_errors = 0

        if self.abort_on_tool_error and has_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT
        elif state.consecutive_tool_errors >= self.max_consecutive_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT
