"""
Act stage for the agent loop.

Act maps model tool calls to executable skills.
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.loop.messages import ToolCall, tool_result_message
from src.core.agents.loop.state import AgentLoopState, ToolCallRecord
from src.core.agents.skills import SkillContext, SkillExecutor, SkillRegistry


@dataclass
class Act:
    """Action stage of the agent loop."""

    registry: SkillRegistry
    executor: SkillExecutor
    tool_dependencies: Optional[Mapping[str, Any]] = None
    context_builder: Optional[Callable[[Any], SkillContext]] = None

    async def run(
        self,
        state: AgentLoopState,
        tool_calls: List[ToolCall],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for call in tool_calls:
            result = await self._execute_one(state, call)
            results.append(result)

        return results

    async def _execute_one(
        self,
        state: AgentLoopState,
        call: ToolCall,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        call_id = call.id
        tool_name = call.name

        try:
            arguments = self._normalize_args(call.arguments)
        except Exception as e:
            return self._record_error(
                state=state,
                call_id=call_id,
                tool_name=tool_name,
                arguments={},
                status="invalid_arguments",
                message=str(e),
                started=started,
            )

        skill = self.registry.get(tool_name)
        if not skill or not skill.is_executable:
            return self._record_error(
                state=state,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                status="not_found",
                message=f"Tool '{tool_name}' not found or not executable",
                started=started,
            )

        try:
            ctx = self._build_context(skill)
            output = await self.executor.execute(skill, ctx, **arguments)
        except Exception as e:
            return self._record_error(
                state=state,
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                status="error",
                message=str(e),
                started=started,
            )

        state.tool_call_history.append(
            ToolCallRecord(
                step=state.step,
                tool_call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                status="success",
                result=output,
                duration_ms=self._duration_ms(started),
            )
        )
        return tool_result_message(
            tool_call_id=call_id,
            name=tool_name,
            content=output,
            is_error=False,
        )

    def _record_error(
        self,
        state: AgentLoopState,
        call_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        message: str,
        started: float,
    ) -> Dict[str, Any]:
        state.tool_call_history.append(
            ToolCallRecord(
                step=state.step,
                tool_call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                status=status,
                error_message=message,
                duration_ms=self._duration_ms(started),
            )
        )
        return tool_result_message(
            tool_call_id=call_id,
            name=tool_name,
            content=message,
            is_error=True,
        )

    def _build_context(self, skill: Any) -> SkillContext:
        if self.context_builder:
            return self.context_builder(skill)

        ctx = SkillContext.from_dependencies(self.tool_dependencies)
        for dep in skill.dependencies:
            getattr(ctx, dep)
        return ctx

    def _normalize_args(self, raw_args: Any) -> Dict[str, Any]:
        if raw_args is None:
            return {}
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            if not raw_args.strip():
                return {}
            parsed = json.loads(raw_args)
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments JSON must be an object")
            return parsed
        raise ValueError(f"Unsupported tool arguments type: {type(raw_args).__name__}")

    def _duration_ms(self, started: float) -> float:
        return (time.monotonic() - started) * 1000


__all__ = ["Act"]
