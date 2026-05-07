"""
Continuous improvement capture for agent loop runs.

The default implementation is intentionally small: callers can plug in a store
to persist run summaries for later evaluation or prompt/tool tuning.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from src.core.agents.state import AgentLoopResult, AgentLoopState


@dataclass(frozen=True)
class ImprovementRecord:
    """Summary of one completed agent run."""

    goal: str
    success: bool
    stop_reason: str
    total_steps: int
    tool_calls_count: int
    final_answer: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run(
        cls,
        state: AgentLoopState,
        result: AgentLoopResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ImprovementRecord":
        return cls(
            goal=state.goal,
            success=result.success,
            stop_reason=result.stop_reason.value,
            total_steps=result.total_steps,
            tool_calls_count=result.tool_calls_count,
            final_answer=result.final_answer,
            metadata=dict(metadata or {}),
        )


class ImprovementStore(Protocol):
    """Persistence boundary for improvement records."""

    def save(self, record: ImprovementRecord) -> Any: ...


@dataclass
class InMemoryImprovementStore:
    """Simple in-memory store useful for tests and demos."""

    records: List[ImprovementRecord] = field(default_factory=list)

    def save(self, record: ImprovementRecord) -> None:
        self.records.append(record)


@dataclass
class ContinuousImprovement:
    """Captures completed run summaries through an optional store."""

    store: Optional[ImprovementStore] = None

    async def capture(
        self,
        state: AgentLoopState,
        result: AgentLoopResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ImprovementRecord]:
        if self.store is None:
            return None

        record = ImprovementRecord.from_run(state, result, metadata)
        saved = self.store.save(record)
        if inspect.isawaitable(saved):
            await saved
        return record


__all__ = [
    "ContinuousImprovement",
    "ImprovementRecord",
    "ImprovementStore",
    "InMemoryImprovementStore",
]
