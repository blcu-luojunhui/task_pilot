"""
Agent Loop - 整合 Think-Act-Observe 循环

这个模块整合了原来 loop/ 目录下的三个阶段：
- Think: 思考和规划
- Act: 执行动作
- Observe: 观察结果
"""

import asyncio
import inspect
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from ..state import AgentLoopState, StopReason, ToolCallRecord
from ..state.protocol import ToolCall, get_tool_calls, tool_result_message
from ..state.context import ContextWindowManager
from ..capabilities.skills import SkillContext, SkillExecutor, SkillRegistry, MappingResolver
from ..exceptions import ToolNotFoundError, ToolExecutionError
from .prompting import PromptAssembler

logger = logging.getLogger("agent.loop")

# Type alias for planner
AssistantPlanner = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass
class Think:
    """思考阶段 - 规划下一步动作"""

    planner: AssistantPlanner
    context_manager: Optional[ContextWindowManager] = None
    prompt_assembler: Optional[PromptAssembler] = None
    memory_manager: Optional[Any] = None  # MemoryManager, 注入相关记忆
    show_prompt: bool = False  # 是否打印发给 LLM 的完整 prompt
    is_cancelled: Optional[Callable[[], bool]] = None  # 暂停/停止检查回调
    publish_event: Optional[Callable[..., Any]] = None  # 发布 prompt_assembled 事件供前端检查器使用
    stream_callback: Optional[Callable[[str], Any]] = None  # token 级别流式回调

    async def run(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        """执行思考阶段"""
        messages = list(state.messages)

        # 组装 prompt
        tools_spec = None
        if self.prompt_assembler:
            system_msg = self.prompt_assembler.assemble(state)
            messages = [system_msg] + messages
            content = system_msg.get("content", "")
            logger.debug(
                "[%s] Think  | prompt assembled (%d chars):\n%s",
                state.trace_id,
                len(content),
                content,
            )
            # 提取 tools spec（如果 prompt assembler 提供了）
            if hasattr(self.prompt_assembler, "knowledge_selector") and hasattr(
                self.prompt_assembler.knowledge_selector, "registry"
            ):
                try:
                    tools_spec = self.prompt_assembler.knowledge_selector.registry.to_tool_specs()
                except Exception:
                    tools_spec = None

        # 注入相关记忆（插在 system prompt 之后）
        if self.memory_manager:
            relevant = self.memory_manager.retrieve(query=state.goal, k=3)
            if relevant:
                memory_msg = {
                    "role": "system",
                    "content": "[Relevant memories from earlier steps]\n" + "\n".join(relevant),
                }
                messages.insert(1, memory_msg)
                logger.debug(
                    "[%s] Think  | injected %d relevant memories",
                    state.trace_id,
                    len(relevant),
                )

        # 压缩上下文
        if self.context_manager:
            before_count = len(messages)
            messages = await self.context_manager.compact_if_needed(messages)
            if len(messages) < before_count:
                logger.debug(
                    "[%s] Think  | context compacted: %d → %d messages",
                    state.trace_id,
                    before_count,
                    len(messages),
                )

        # 发布 prompt_assembled 事件（供前端 Prompt Inspector 使用）
        if self.publish_event:
            try:
                result = self.publish_event(
                    "prompt_assembled",
                    {
                        "messages": messages,
                        "tools_spec": tools_spec,
                    },
                    step=state.step,
                )
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.debug("[%s] Think  | publish_event failed for prompt_assembled", state.trace_id)

        if self.show_prompt:
            logger.debug(
                "[%s] Think  | sending %d messages to LLM:\n%s",
                state.trace_id,
                len(messages),
                self._format_messages(messages),
            )
        else:
            logger.debug(
                "[%s] Think  | sending %d messages to LLM",
                state.trace_id,
                len(messages),
            )

        # 调用 planner 前检查是否已取消
        if self.is_cancelled and self.is_cancelled():
            state.stop_reason = StopReason.USER_CANCELLED
            return None

        # 调用 planner
        try:
            result = await self.planner(messages, state.step, stream_callback=self.stream_callback)
            # 累积 token 使用量
            if result and "_usage" in result:
                usage = result.pop("_usage")
                for key in ("prompt", "completion", "total"):
                    state.token_usage[key] = state.token_usage.get(key, 0) + usage.get(key, 0)
            return result
        except Exception:
            logger.exception("Agent planner failed at step %s", state.step)
            state.stop_reason = StopReason.LLM_ERROR_ABORT
            return None

    @staticmethod
    def _format_messages(messages: List[Dict[str, Any]]) -> str:
        """格式化消息列表用于日志输出"""
        lines = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")

            # 头部
            header = f"  [{i + 1}] role={role}"
            if tool_call_id:
                header += f"  tool_call_id={tool_call_id}"

            # 内容
            if content:
                display = content[:300] + "..." if len(content) > 300 else content
                lines.append(f"{header}")
                for line in display.split("\n"):
                    lines.append(f"      {line}")
            else:
                lines.append(f"{header}  (no content)")

            # tool_calls
            if tool_calls:
                import json

                for tc in tool_calls:
                    func = tc.get("function", tc)
                    name = func.get("name", tc.get("name", "?"))
                    args = func.get("arguments", "")
                    if isinstance(args, str) and len(args) > 100:
                        args = args[:100] + "..."
                    lines.append(f"      tool_call: {name}({args})")

        return "\n".join(lines)


@dataclass
class Act:
    """执行阶段 - 执行工具调用"""

    registry: SkillRegistry
    executor: SkillExecutor
    tool_dependencies: Optional[Mapping[str, Any]] = None
    context_builder: Optional[Callable[[Any], SkillContext]] = None
    max_tool_result_length: int = 2000
    max_concurrency: int = 5
    is_cancelled: Optional[Callable[[], bool]] = None  # 暂停/停止检查回调

    def __post_init__(self):
        if self.max_concurrency > 0:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)

    async def run(self, state: AgentLoopState, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
        """执行工具调用"""
        if not tool_calls:
            return []
        if len(tool_calls) == 1:
            return [await self._execute_one(state, tool_calls[0])]
        tasks = [self._execute_one(state, call) for call in tool_calls]
        return list(await asyncio.gather(*tasks))

    async def _execute_one(self, state: AgentLoopState, call: ToolCall) -> Dict[str, Any]:
        if hasattr(self, "_semaphore"):
            async with self._semaphore:
                return await self._execute_one_impl(state, call)
        return await self._execute_one_impl(state, call)

    async def _execute_one_impl(self, state: AgentLoopState, call: ToolCall) -> Dict[str, Any]:
        """执行单个工具调用"""
        # 工具执行前检查是否已取消
        if self.is_cancelled and self.is_cancelled():
            return tool_result_message(call.id, "Cancelled: agent stopped by user")

        started = time.monotonic()
        call_id = call.id
        tool_name = call.name

        # 解析参数（ToolCall.arguments 已经是 dict）
        arguments = call.arguments

        # 查找 skill
        skill = self.registry.get(tool_name)
        if not skill:
            raise ToolNotFoundError(tool_name)

        # 权限检查由 SkillExecutor 统一处理

        # 构建上下文
        if self.context_builder:
            context = self.context_builder(state)
        else:
            resolver = MappingResolver(self.tool_dependencies)
            context = SkillContext(_resolver=resolver)

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
            return tool_result_message(call_id, self._smart_truncate(result, self.max_tool_result_length))
        except asyncio.CancelledError:
            raise
        except ToolNotFoundError as e:
            logger.warning("Tool not found: %s", e.tool_name)
            return self._record_error(state, call_id, tool_name, str(e))
        except ToolExecutionError as e:
            logger.warning("Tool '%s' execution failed: %s", tool_name, e)
            return self._record_error(state, call_id, tool_name, str(e))
        except Exception as e:
            logger.warning("Tool '%s' unexpected error: %s", tool_name, e)
            return self._record_error(state, call_id, tool_name, f"{type(e).__name__}: {e}")

    def _record_error(self, state, call_id, tool_name, error_msg):
        """记录错误"""
        state.tool_calls.append(ToolCallRecord(tool_name=tool_name, tool_input={}, error=error_msg))
        return tool_result_message(call_id, f"Error: {error_msg}")

    @staticmethod
    def _smart_truncate(result: Any, max_length: int) -> str:
        """结构化截断，保留 JSON 可解析性，防止硬截断破坏结构导致 LLM 解析错误"""
        result_str = str(result)
        if len(result_str) <= max_length:
            return result_str

        if isinstance(result, list):
            truncated = result[:5]
            suffix = f"\n[TRUNCATED: showing 5/{len(result)} items, {len(result_str)} chars]"
            return json.dumps(truncated, ensure_ascii=False, default=str) + suffix

        if isinstance(result, dict):
            truncated = {}
            for k, v in list(result.items())[:10]:
                v_str = str(v)
                truncated[k] = v if len(v_str) < 100 else v_str[:100] + "..."
            suffix = f"\n[TRUNCATED: showing 10/{len(result)} keys, {len(result_str)} chars]"
            return json.dumps(truncated, ensure_ascii=False, default=str) + suffix

        return result_str[:max_length] + f"\n[TRUNCATED at {max_length} chars]"


@dataclass
class Observe:
    """观察阶段 - 处理执行结果"""

    abort_on_tool_error: bool = False
    max_consecutive_errors: int = 3
    memory_manager: Optional[Any] = None  # MemoryManager, 写入有用结果

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
            content = assistant_message.get("content")
            if not content or not str(content).strip():
                state.stop_reason = StopReason.LLM_ERROR_ABORT
                return
            state.final_answer = content
            state.stop_reason = StopReason.MODEL_FINAL
            return

        state.add_tool_results(tool_results)

        # 写入记忆：成功的工具结果存入短期记忆
        if self.memory_manager and tool_results:
            for i, result in enumerate(tool_results):
                content = str(result.get("content", ""))
                if not content.startswith("Error:") and content.strip():
                    tool_name = tool_calls[i].name if i < len(tool_calls) else "unknown"
                    self.memory_manager.add(
                        content=content,
                        metadata={"step": state.step, "tool": tool_name},
                    )

        error_count = sum(
            1 for r in tool_results if str(r.get("content", "")).startswith("Error:")
        )
        if error_count == len(tool_results) and tool_results:
            # 本步全部工具都失败才累加
            state.consecutive_tool_errors += 1
        elif error_count == 0:
            state.consecutive_tool_errors = 0
        # 部分失败不累加也不清零，保留之前的状态

        if self.abort_on_tool_error and has_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT
        elif state.consecutive_tool_errors >= self.max_consecutive_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT


__all__ = ["Think", "Act", "Observe", "AssistantPlanner"]
