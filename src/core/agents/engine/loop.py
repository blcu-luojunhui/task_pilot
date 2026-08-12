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
from ..capabilities.skills import (
    MappingResolver,
    RiskLevel,
    SkillContext,
    SkillExecutor,
    SkillRegistry,
)
from ..capabilities.skills.tool_result_memory import (
    annotate_tool_message, collapse_old_tool_results,
)
from ..capabilities.skills.security import redact_sensitive_data, wrap_untrusted_tool_output
from ..exceptions import ToolNotFoundError, ToolExecutionError
from .prompting import PromptAssembler
from ..execution.ledger import LedgerState, ToolExecutionLedgerError

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
    event_bus: Optional[Any] = None  # TraceEventBus，用于发布 chat.token_delta

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
            query = self.memory_manager.build_memory_query(state)
            # 优先使用异步检索（支持语义后端），回退同步检索
            if hasattr(self.memory_manager, "aretrieve"):
                result = self.memory_manager.aretrieve(query=query, k=3)
                if inspect.isawaitable(result):
                    relevant = await result
                else:
                    relevant = self.memory_manager.retrieve(query=query, k=3)
            else:
                relevant = self.memory_manager.retrieve(query=query, k=3)
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
        # 折叠旧的超长 tool 结果，节省上下文 token
        messages = collapse_old_tool_results(messages)

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

        # 构建流式回调（同时支持原有 stream_callback + SSE token_delta 事件）
        _original_stream = self.stream_callback
        _ebus = self.event_bus
        _trace_id = state.trace_id
        _step = state.step

        async def _wrapped_stream(token: str) -> None:
            if _original_stream:
                result = _original_stream(token)
                if inspect.isawaitable(result):
                    await result
            if _ebus:
                try:
                    _ebus.publish(
                        trace_id=_trace_id,
                        event_type="token_delta",
                        data={"delta": token},
                        source="agent",
                        step=_step,
                        persist=False,
                    )
                except Exception:
                    pass

        async def _on_llm_retry(detail: Dict[str, Any]) -> None:
            if _ebus:
                try:
                    _ebus.publish(
                        trace_id=_trace_id,
                        event_type="llm_retry",
                        data=detail,
                        source="agent",
                        step=_step,
                    )
                except Exception:
                    pass

        # 调用 planner
        try:
            result = await self.planner(
                messages, state.step,
                stream_callback=_wrapped_stream if (_original_stream or _ebus) else None,
                on_retry=_on_llm_retry,
            )
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
    artifact_store: Optional[Any] = None  # OPT-5: ArtifactStore
    enable_offload: bool = False  # OPT-5: 上下文卸载开关
    offload_threshold_chars: int = 4000
    event_bus: Optional[Any] = None  # TraceEventBus，用于发布 chat.tool_call_* 事件
    execution_ledger: Optional[Any] = None

    def __post_init__(self):
        if self.max_concurrency > 0:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)

    async def run(self, state: AgentLoopState, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
        """执行工具调用"""
        if not tool_calls:
            return []
        has_side_effect = any(
            (skill := self.registry.get(call.name)) is not None
            and skill.risk_level in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}
            for call in tool_calls
        )
        if len(tool_calls) == 1 or has_side_effect:
            results = []
            for call in tool_calls:
                results.append(annotate_tool_message(await self._execute_one(state, call)))
                if state.pending_reconciliation:
                    break
            return results
        tasks = [self._execute_one(state, call) for call in tool_calls]
        return [annotate_tool_message(r) for r in list(await asyncio.gather(*tasks))]

    @staticmethod
    def _mark_reconciliation(
        state: AgentLoopState,
        call: ToolCall,
        reason: str,
    ) -> None:
        state.stop_reason = StopReason.EXECUTION_IN_DOUBT
        state.pending_reconciliation = {
            "tool_call_id": call.id,
            "tool_name": call.name,
            "arguments": redact_sensitive_data(call.arguments),
            "ledger_status": "running",
            "reason": reason,
        }

    async def _execute_one(self, state: AgentLoopState, call: ToolCall) -> Dict[str, Any]:
        if hasattr(self, "_semaphore"):
            async with self._semaphore:
                return await self._execute_one_impl(state, call)
        return await self._execute_one_impl(state, call)

    async def _execute_one_impl(self, state: AgentLoopState, call: ToolCall) -> Dict[str, Any]:
        """执行单个工具调用"""
        if self.is_cancelled and self.is_cancelled():
            return self._tool_end(state, call.id, call.name,
                                 tool_result_message(call.id, "Cancelled: agent stopped by user"), False)

        started = time.monotonic()
        call_id = call.id
        tool_name = call.name
        arguments = call.arguments

        # 发布 tool_call_start
        self._publish_tool_event(state, "tool_call_start",
                                 {"call_id": call_id, "tool_name": tool_name,
                                  "arguments": redact_sensitive_data(arguments)})

        skill = self.registry.get(tool_name)
        if not skill:
            raise ToolNotFoundError(tool_name)

        uses_ledger = (
            self.execution_ledger is not None
            and skill.risk_level in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}
        )
        if uses_ledger:
            try:
                self.executor.validate_call(skill, arguments)
                claim = await self.execution_ledger.claim(
                    state.trace_id,
                    call_id,
                    tool_name,
                    arguments,
                )
            except Exception as exc:
                return self._tool_end(
                    state,
                    call_id,
                    tool_name,
                    self._record_error(state, call_id, tool_name, str(exc)),
                    False,
                )
            if claim.state == LedgerState.COMPLETED:
                state.tool_calls.append(
                    ToolCallRecord(
                        tool_name=tool_name,
                        tool_input=redact_sensitive_data(arguments),
                        tool_output=claim.result_content or "",
                    )
                )
                replayed = tool_result_message(
                    call_id,
                    claim.result_content or "",
                )
                self._publish_tool_event(
                    state,
                    "tool_call_replayed",
                    {"call_id": call_id, "tool_name": tool_name, "status": "completed"},
                )
                return self._tool_end(state, call_id, tool_name, replayed, True)
            if claim.state == LedgerState.FAILED:
                failed = claim.error_message or "previous execution failed"
                return self._tool_end(
                    state,
                    call_id,
                    tool_name,
                    self._record_error(
                        state,
                        call_id,
                        tool_name,
                        failed,
                    ),
                    False,
                )
            if claim.state == LedgerState.IN_DOUBT:
                reason = (
                    "previous process may have completed the side effect; "
                    "automatic retry is blocked"
                )
                self._mark_reconciliation(state, call, reason)
                return self._tool_end(
                    state,
                    call_id,
                    tool_name,
                    self._record_error(
                        state,
                        call_id,
                        tool_name,
                        f"execution_in_doubt: {reason}",
                    ),
                    False,
                )

        if self.context_builder:
            context = self.context_builder(state)
        else:
            resolver = MappingResolver(self.tool_dependencies)
            context = SkillContext(_resolver=resolver)
        context.trace_id = state.trace_id
        context.step = state.step
        context.tool_call_id = call_id
        context.tool_name = tool_name

        try:
            result = await (
                self.executor.execute_prevalidated(skill, context, **arguments)
                if uses_ledger
                else self.executor.execute(skill, context, **arguments)
            )
            duration = time.monotonic() - started
            safe_result = redact_sensitive_data(result)
            result_str = str(safe_result)

            if self.enable_offload and self.artifact_store and len(result_str) > self.offload_threshold_chars:
                try:
                    ref = await self.artifact_store.put(
                        trace_id=state.trace_id, tool_name=tool_name,
                        step=state.step, content=result_str)
                    msg = tool_result_message(call_id,
                        f"[Large result offloaded to artifact://{ref.id}, "
                        f"{ref.total_lines} lines / {ref.total_chars} chars. "
                        f"Preview: {ref.preview}]\n"
                        f"Call read_artifact(id=\"{ref.id}\") to read the full content.")
                    if uses_ledger:
                        await self.execution_ledger.complete(
                            state.trace_id,
                            call_id,
                            msg["content"],
                        )
                    state.tool_calls.append(
                        ToolCallRecord(
                            tool_name=tool_name,
                            tool_input=redact_sensitive_data(arguments),
                            tool_output=result_str,
                            duration_ms=duration * 1000,
                        )
                    )
                    return self._tool_end(state, call_id, tool_name, msg, True)
                except Exception:
                    logger.warning("Artifact offload failed, falling back to truncation", exc_info=True)

            content = self._smart_truncate(safe_result, self.max_tool_result_length)
            msg = tool_result_message(call_id, wrap_untrusted_tool_output(content))
            if uses_ledger:
                await self.execution_ledger.complete(state.trace_id, call_id, msg["content"])
            state.tool_calls.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    tool_input=redact_sensitive_data(arguments),
                    tool_output=result_str,
                    duration_ms=duration * 1000,
                )
            )
            return self._tool_end(state, call_id, tool_name, msg, True)
        except asyncio.CancelledError:
            raise
        except ToolNotFoundError as e:
            logger.warning("Tool not found: %s", e.tool_name)
            return self._tool_end(state, call_id, tool_name, self._record_error(state, call_id, tool_name, str(e)), False)
        except ToolExecutionError as e:
            logger.warning("Tool '%s' execution failed: %s", tool_name, e)
            if uses_ledger:
                try:
                    await self.execution_ledger.fail(state.trace_id, call_id, str(e))
                except ToolExecutionLedgerError:
                    logger.exception("Failed to persist tool execution failure")
                    self._mark_reconciliation(
                        state,
                        call,
                        "tool raised an error but its ledger outcome could not be persisted",
                    )
            return self._tool_end(state, call_id, tool_name, self._record_error(state, call_id, tool_name, str(e)), False)
        except Exception as e:
            logger.warning("Tool '%s' unexpected error: %s", tool_name, e)
            if uses_ledger:
                reason = (
                    "tool returned but its completion could not be persisted"
                    if isinstance(e, ToolExecutionLedgerError)
                    else "tool raised unexpectedly after execution began"
                )
                self._mark_reconciliation(state, call, reason)
            return self._tool_end(state, call_id, tool_name, self._record_error(state, call_id, tool_name, f"{type(e).__name__}: {e}"), False)

    def _publish_tool_event(self, state: AgentLoopState, event_type: str, data: Dict[str, Any]) -> None:
        _bus = self.event_bus
        if _bus:
            try:
                _bus.publish(trace_id=state.trace_id, event_type=event_type,
                             data=data, source="agent", step=state.step)
            except Exception:
                pass

    def _tool_end(self, state: AgentLoopState, call_id: str, tool_name: str,
                  result_msg: Dict[str, Any], ok: bool) -> Dict[str, Any]:
        self._publish_tool_event(state, "tool_call_end",
                                 {"call_id": call_id, "tool_name": tool_name, "ok": ok,
                                  "result": result_msg.get("content", "")[:4096]})
        return result_msg

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

        has_errors = error_count > 0
        if self.abort_on_tool_error and has_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT
        elif state.consecutive_tool_errors >= self.max_consecutive_errors:
            state.stop_reason = StopReason.TOOL_ERROR_ABORT


__all__ = ["Think", "Act", "Observe", "AssistantPlanner"]
