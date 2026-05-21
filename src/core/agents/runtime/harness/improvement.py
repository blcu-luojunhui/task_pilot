"""
Continuous improvement capture for agent loop runs.

Captures structured run summaries for post-hoc analysis and LLM-based reflection.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING

from src.core.agents.state import AgentLoopResult, AgentLoopState, ToolCallRecord

if TYPE_CHECKING:
    from src.core.agents.capabilities.llm.base import LLMProvider


@dataclass(frozen=True)
class ImprovementRecord:
    """Summary of one completed agent run, with fields for tuning and reflection."""

    goal: str
    success: bool
    stop_reason: str
    total_steps: int
    tool_calls_count: int
    final_answer: Optional[str]

    # 调优必需字段
    failed_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: Dict[str, int] = field(default_factory=dict)  # prompt/completion/total
    prompt_version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run(
        cls,
        state: AgentLoopState,
        result: AgentLoopResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ImprovementRecord":
        failed = [
            {"tool_name": tc.tool_name, "error": tc.error}
            for tc in state.tool_calls
            if tc.error
        ]
        return cls(
            goal=state.goal,
            success=result.success,
            stop_reason=result.stop_reason.value,
            total_steps=result.total_steps,
            tool_calls_count=result.tool_calls_count,
            final_answer=result.final_answer,
            failed_tool_calls=failed,
            token_usage=dict(state.token_usage),
            prompt_version=metadata.get("prompt_version", "") if metadata else "",
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
class DBImprovementStore:
    """Persists improvement records to agent_run_summaries table."""

    mysql_pool: Any  # AsyncMySQLPool, 避免循环导入用 Any

    async def save(self, record: ImprovementRecord) -> None:
        import json

        sql = (
            "INSERT INTO agent_run_summaries "
            "(trace_id, goal, success, stop_reason, total_steps, tool_calls_count, "
            "final_answer, failed_tool_calls, token_usage, prompt_version, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "success=VALUES(success), stop_reason=VALUES(stop_reason), "
            "total_steps=VALUES(total_steps), tool_calls_count=VALUES(tool_calls_count), "
            "final_answer=VALUES(final_answer), failed_tool_calls=VALUES(failed_tool_calls), "
            "token_usage=VALUES(token_usage), metadata=VALUES(metadata)"
        )
        params = (
            record.metadata.get("trace_id", ""),
            record.goal,
            1 if record.success else 0,
            record.stop_reason,
            record.total_steps,
            record.tool_calls_count,
            record.final_answer,
            json.dumps(record.failed_tool_calls, ensure_ascii=False),
            json.dumps(record.token_usage, ensure_ascii=False),
            record.prompt_version or "",
            json.dumps(record.metadata, ensure_ascii=False),
        )
        await self.mysql_pool.async_save(sql, params)


@dataclass
class ContinuousImprovement:
    """Captures completed run summaries and optionally runs LLM-based reflection."""

    store: Optional[ImprovementStore] = field(default_factory=InMemoryImprovementStore)
    reflection_provider: Optional["LLMProvider"] = None  # 用于 analyze()

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

    async def analyze(self, record: ImprovementRecord) -> Optional[str]:
        """分析运行结果，生成改进建议（需要 reflection_provider）"""
        if not self.reflection_provider or record.success:
            return None

        from src.core.agents.capabilities.llm.base import LLMMessage

        failed_str = "\n".join(
            f"  - {fc['tool_name']}: {fc['error']}" for fc in record.failed_tool_calls
        ) or "(none)"

        prompt = (
            f"Task: {record.goal}\n"
            f"Stop reason: {record.stop_reason}\n"
            f"Total steps: {record.total_steps}, tool calls: {record.tool_calls_count}\n"
            f"Failed tool calls:\n{failed_str}\n"
            f"Token usage: prompt={record.token_usage.get('prompt', 0)}, "
            f"completion={record.token_usage.get('completion', 0)}, "
            f"total={record.token_usage.get('total', 0)}\n\n"
            "Analyze why this agent run failed and suggest concrete improvements "
            "(prompt changes, tool fixes, budget adjustments). Be specific and actionable."
        )

        try:
            response = await self.reflection_provider.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=500,
            )
            return response.content
        except Exception:
            return None


__all__ = [
    "ContinuousImprovement",
    "ImprovementRecord",
    "ImprovementStore",
    "InMemoryImprovementStore",
]
