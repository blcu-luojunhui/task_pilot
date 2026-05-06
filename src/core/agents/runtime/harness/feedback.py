"""
Feedback loop for the agent loop harness.

Feedback providers can add messages after a step so the next Think stage sees
runtime feedback from evaluation, guardrails, or environment signals.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from src.core.agents.state import AgentLoopState

FeedbackMessage = Dict[str, Any]
FeedbackOutput = Optional[Union[str, FeedbackMessage, List[FeedbackMessage]]]
FeedbackProvider = Callable[[AgentLoopState, Dict[str, Any]], Any]


@dataclass
class FeedbackLoop:
    """Collects and appends feedback messages between loop steps."""

    providers: List[FeedbackProvider] = field(default_factory=list)

    async def run(
        self,
        state: AgentLoopState,
        payload: Optional[Dict[str, Any]] = None,
    ) -> List[FeedbackMessage]:
        messages: List[FeedbackMessage] = []

        for provider in self.providers:
            output = provider(state, payload or {})
            if inspect.isawaitable(output):
                output = await output
            messages.extend(self._normalize(output))

        if messages:
            state.messages.extend(messages)
        return messages

    def _normalize(self, output: FeedbackOutput) -> List[FeedbackMessage]:
        if output is None:
            return []
        if isinstance(output, str):
            return [{"role": "system", "name": "feedback", "content": output}]
        if isinstance(output, dict):
            return [output]
        return list(output)


__all__ = [
    "FeedbackLoop",
    "FeedbackMessage",
    "FeedbackOutput",
    "FeedbackProvider",
]
