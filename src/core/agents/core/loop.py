"""
Agent Loop - 整合 Think-Act-Observe 循环

这个模块整合了原来 loop/ 目录下的三个阶段：
- Think: 思考和规划
- Act: 执行动作
- Observe: 观察结果
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from ..state import AgentLoopState, StopReason, ToolCallRecord
from ..state.protocol import ToolCall, get_tool_calls, tool_result_message
from ..state.context import ContextWindowManager
from ..capabilities.skills import SkillContext, SkillExecutor, SkillRegistry
from ..capabilities.skills.guard import PermissionGuard

logger = logging.getLogger(__name__)

# Type alias for planner
AssistantPlanner = Callable[[List[Dict[str, Any]], int], Awaitable[Dict[str, Any]]]


@dataclass
class Think:
    """思考阶段 - 规划下一步动作"""

    planner: AssistantPlanner
    context_manager: Optional[ContextWindowManager] = None
    prompt_assembler: Optional[Callable] = None
    stream_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None

    async def run(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        """执行思考阶段"""
        messages = list(state.messages)

        # 组装 prompt
        if self.prompt_assembler:
            messages = [self.prompt_assembler.assemble(state)] + messages

        # 压缩上下文
        if self.context_manager:
            messages = self.context_manager.compact_if_needed(messages)

        # 调用 planner
        try:
            return await self.planner(messages, state.step)
        except Exception:
            logger.exception("Agent planner failed at step %s", state.step)
            state.stop_reason = StopReason.LLM_ERROR_ABORT
            return None


@dataclass
class Act:
    """执行阶段 - 执行工具调用"""

    registry: SkillRegistry
    executor: SkillExecutor
    tool_dependencies: Optional[Mapping[str, Any]] = None
    context_builder: Optional[Callable[[Any], SkillContext]] = None
    max_tool_result_length: int = 2000
    permission_guard: Optional[PermissionGuard] = None

    async def run(self, state: AgentLoopState, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
        """执行工具调用"""
        if not tool_calls:
            return []
        if len(tool_calls) == 1:
            return [await self._execute_one(state, tool_calls[0])]
        tasks = [self._execute_one(state, call) for call in tool_calls]
        return list(await asyncio.gather(*tasks))

    async def _execute_one(self, state: AgentLoopState, call: ToolCall) -> Dict[str, Any]:
        """执行单个工具调用"""
        started = time.monotonic()
        call_id = call.id
        tool_name = call.name

        # 解析参数（ToolCall.arguments 已经是 dict）
        arguments = call.arguments

        # 查找 skill
        skill = self.registry.get(tool_name)
        if not skill:
            return self._record_error(state, call_id, tool_name, f"Unknown tool: {tool_name}")

        # 权限检查
        if self.permission_guard:
            denial = self.permission_guard.check(skill)
            if denial:
                return self._record_error(state, call_id, tool_name, denial)

        # 构建上下文
        context = self.context_builder(state) if self.context_builder else SkillContext()

        # 执行
        try:
            result = await self.executor.execute(skill, context, **arguments)
            duration = time.monotonic() - started
            state.tool_calls.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    tool_input=arguments,
                    tool_output=str(result),
                    duration_ms=duration * 1000,
                )
            )
            return tool_result_message(call_id, str(result)[:self.max_tool_result_length])
        except Exception as e:
            logger.warning(f"Tool '{tool_name}' execution failed: {e}")
            return self._record_error(state, call_id, tool_name, str(e))

    def _record_error(self, state, call_id, tool_name, error_msg):
        """记录错误"""
        state.tool_calls.append(
            ToolCallRecord(tool_name=tool_name, tool_input={}, error=error_msg)
        )
        return tool_result_message(call_id, f"Error: {error_msg}", is_error=True)


@dataclass
class Observe:
    """观察阶段 - 处理执行结果"""

    abort_on_tool_error: bool = False
    max_consecutive_errors: int = 3

    def run(
        self,
        state: AgentLoopState,
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> None:
        """处理观察结果"""
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


__all__ = ["Think", "Act", "Observe", "AssistantPlanner"]
