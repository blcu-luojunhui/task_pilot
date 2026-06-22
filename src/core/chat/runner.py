"""ChatTurnRunner：极简 while 循环，替代 Agent harness。

每轮 = LLM 流式调用 → 解析 tool_calls → 风险分级 → 执行或暂停。
不引入 budget / feedback_loop / improvement / context_window。

模式切换：
- chat 模式（默认）：只暴露 escalate_to_agent + 只读查询工具
- agentic 模式：暴露完整工具集（plan_tasks / run_task 等），走 propose-confirm
LLM 调用 escalate_to_agent 后自动切换到 agentic 模式，同一轮内保持。
"""
from __future__ import annotations

import json as _json
import time as _time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMMessage
from src.core.agents.capabilities.skills import (
    Skill,
    SkillContext,
    SkillExecutor,
    get_global_registry,
)
from src.core.agents.capabilities.skills.serializer import OpenAIAdapter, ToolSpecSerializer
from src.core.chat.events import ChatEventType
from src.core.chat.risk import is_chat_mode_tool, is_high_risk
from src.infra.streaming import TraceEventBus

_MAX_ITERATIONS = 10
_TOKEN_FLUSH_INTERVAL = 0.016
_TOKEN_FLUSH_CHARS = 48
_MAX_EVENT_PAYLOAD_CHARS = 4096

_ESCALATE_TOOL_NAME = "escalate_to_agent"


@dataclass
class ChatTurnResult:
    status: str  # "completed" | "pending_confirmation" | "cancelled"
    content: str
    proposed_tool_calls: Optional[List[Dict]] = None
    tool_call_results: Optional[List[Dict]] = None
    token_usage: Optional[Dict] = None


class ChatTurnRunner:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tools: List[Skill],
        trace_id: str,
        event_bus: TraceEventBus,
        cancel_checker: Callable[[], Awaitable[bool]],
        tool_dependencies: Optional[Dict[str, Any]] = None,
        on_escalate: Optional[Callable[[], Awaitable[None]]] = None,
        initial_mode: str = "chat",
        skip_risk_check: bool = False,
    ):
        self._provider = llm_provider
        self._tools = tools
        self._trace_id = trace_id
        self._event_bus = event_bus
        self._cancel_checker = cancel_checker
        self._tool_deps = tool_dependencies or {}
        self._executor = SkillExecutor(validate_params=False)
        self._serializer = ToolSpecSerializer(OpenAIAdapter())
        self._mode = initial_mode  # "chat" | "agentic"
        self._on_escalate = on_escalate
        self._skip_risk_check = skip_risk_check
        self._step = 0
        self._source = "agent" if initial_mode == "agentic" else "runner"
        self._goal_label = ""

    def _active_tools(self) -> List[Skill]:
        """根据当前 mode 过滤暴露给 LLM 的工具。"""
        if self._mode == "agentic":
            return [t for t in self._tools if t.is_executable]
        return [t for t in self._tools if t.is_executable and is_chat_mode_tool(t.name)]

    async def run(
        self,
        messages: List[Dict],
        system_prompt: str,
        *,
        confirmed_tool_calls: Optional[List[Dict]] = None,
    ) -> ChatTurnResult:
        # confirm 续跑意味着之前已经升级到 agentic 模式
        if confirmed_tool_calls:
            self._mode = "agentic"
            if self._on_escalate:
                try:
                    await self._on_escalate()
                except Exception:
                    pass
            await self._publish(ChatEventType.MODE_CHANGED, {
                "mode": "agentic",
                "reason": "confirm 续跑",
            })
            tool_results = await self._execute_tools(confirmed_tool_calls)
            messages = messages + [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": confirmed_tool_calls,
                },
                *tool_results,
            ]

        total_usage: Dict[str, int] = {}
        tool_calls_count = 0
        run_start_ts = _time.monotonic()

        # 发布 harness 兼容的 run_start 事件
        goal = self._goal_label or ""
        if not goal and messages:
            goal = messages[0].get("content", "") or ""
        await self._publish_harness("run_start", {
            "metadata": {"goal": goal, "trace_id": self._trace_id},
            "goal": goal,
        })

        for _ in range(_MAX_ITERATIONS):
            self._step += 1
            if await self._cancel_checker():
                return ChatTurnResult(status="cancelled", content="")

            # 发布 step_start（DAGView 依赖此事件识别步骤边界）
            await self._publish_harness("step_start", {"deps": []})

            # 发布 think_start
            await self._publish_harness("think_start", {})

            full_content, tool_calls, usage = await self._call_llm(messages, system_prompt)

            if usage:
                for k, v in usage.items():
                    total_usage[k] = total_usage.get(k, 0) + v

            # 发布 harness 兼容的 think_end
            await self._publish_harness("think_end", {
                "assistant_message": {
                    "content": full_content,
                    "tool_calls": tool_calls or [],
                },
                "_usage": usage or {},
            })

            if not tool_calls:
                if self._mode == "agentic":
                    self._mode = "chat"
                    await self._publish(ChatEventType.MODE_CHANGED, {
                        "mode": "chat",
                        "reason": "turn 正常结束",
                    })
                await self._publish(ChatEventType.TURN_END, {
                    "content": full_content,
                    "token_usage": total_usage,
                })
                await self._publish_harness("step_end", {})
                await self._publish_harness("run_end", {
                    "result": {
                        "stop_reason": "completed",
                        "total_steps": self._step,
                        "tool_calls_count": tool_calls_count,
                        "token_usage": total_usage,
                        "duration_seconds": round(_time.monotonic() - run_start_ts, 2),
                        "final_answer": full_content,
                    },
                })
                return ChatTurnResult(
                    status="completed",
                    content=full_content,
                    token_usage=total_usage,
                )

            # 检查是否有 escalate_to_agent 调用 → 切模式
            escalate_calls = [
                tc for tc in tool_calls
                if tc["function"]["name"] == _ESCALATE_TOOL_NAME
            ]
            if escalate_calls:
                self._mode = "agentic"
                escalate_reason = ""
                try:
                    escalate_reason = _json.loads(
                        escalate_calls[0]["function"].get("arguments", "{}")
                    ).get("reason", "")
                except Exception:
                    pass
                # 通知外层按需创建 task_manager 记录
                if self._on_escalate:
                    try:
                        await self._on_escalate()
                    except Exception:
                        pass
                await self._publish(ChatEventType.MODE_CHANGED, {
                    "mode": "agentic",
                    "reason": escalate_reason,
                })
                # 执行 escalate（结果只是占位），写 tool 消息让 LLM 知道已升级
                tool_calls_count += len(tool_calls)
                tool_results = await self._execute_tools(tool_calls)
                messages = messages + [
                    {
                        "role": "assistant",
                        "content": full_content,
                        "tool_calls": tool_calls,
                    },
                    *tool_results,
                ]
                await self._publish(ChatEventType.TOOL_CALL_END, {
                    "tool_name": _ESCALATE_TOOL_NAME,
                    "call_id": escalate_calls[0].get("id", ""),
                    "result": {"mode": "agentic"},
                    "ok": True,
                })
                continue

            # 风险分级（仅 agentic 模式下才可能出现 high-risk 工具）
            if not self._skip_risk_check:
                high_risk = [tc for tc in tool_calls if is_high_risk(tc["function"]["name"])]

                if high_risk:
                    await self._publish(ChatEventType.TOOL_CALL_PROPOSED, {
                        "tool_calls": tool_calls,
                    })
                    await self._publish(ChatEventType.TURN_PAUSED, {})
                    await self._publish_harness("step_end", {})
                    await self._publish_harness("run_end", {
                        "result": {
                            "stop_reason": "pending_confirmation",
                            "total_steps": self._step,
                            "tool_calls_count": tool_calls_count,
                            "token_usage": total_usage,
                            "duration_seconds": round(_time.monotonic() - run_start_ts, 2),
                        },
                    })
                    return ChatTurnResult(
                        status="pending_confirmation",
                        content=full_content,
                        proposed_tool_calls=tool_calls,
                        token_usage=total_usage,
                    )

            # 全 low-risk → 直接执行
            tool_calls_count += len(tool_calls)
            tool_results = await self._execute_tools(tool_calls)
            messages = messages + [
                {
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": tool_calls,
                },
                *tool_results,
            ]
            await self._publish_harness("step_end", {})

        await self._publish_harness("run_end", {
            "result": {
                "stop_reason": "max_iterations",
                "total_steps": self._step,
                "tool_calls_count": tool_calls_count,
                "token_usage": total_usage,
                "duration_seconds": round(_time.monotonic() - run_start_ts, 2),
            },
        })
        return ChatTurnResult(status="completed", content="达到最大迭代次数", token_usage=total_usage)

    # ── 内部方法 ────────────────────────────────────────────

    async def _call_llm(
        self, messages: List[Dict], system_prompt: str
    ) -> tuple:
        """通过 SSE 流式调 LLM，逐 chunk 发 token_delta，同时累积 tool_calls。"""
        llm_messages = [LLMMessage(role="system", content=system_prompt)]
        for m in messages:
            llm_messages.append(LLMMessage(
                role=m["role"],
                content=m.get("content") or "",
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
            ))

        active_tools = self._active_tools()
        tool_specs = self._serializer.serialize_many(active_tools)
        openai_tools = [{"type": "function", "function": s} for s in tool_specs]

        payload = {
            "model": self._provider.config.model,
            "messages": [
                {"role": m.role, "content": m.content,
                 **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                 **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {})}
                for m in llm_messages
            ],
            "temperature": self._provider.config.temperature,
            "stream": True,
        }
        if openai_tools:
            payload["tools"] = openai_tools

        headers = {
            "Authorization": f"Bearer {self._provider.config.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._provider.config.base_url}/chat/completions"

        session = self._provider._get_session()
        full_content = ""
        tool_calls_acc: Dict[int, Dict] = {}
        usage_dict: Optional[Dict] = None

        delta_buf: List[str] = []
        last_flush = _time.monotonic()

        async def _flush_delta() -> None:
            nonlocal last_flush
            if not delta_buf:
                return
            merged = "".join(delta_buf)
            delta_buf.clear()
            last_flush = _time.monotonic()
            await self._publish(
                ChatEventType.TOKEN_DELTA,
                {"delta": merged},
                persist=False,
            )

        async with session.post(url, headers=headers, json=payload) as resp:
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data)
                except _json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})

                if "content" in delta and delta["content"]:
                    full_content += delta["content"]
                    delta_buf.append(delta["content"])
                    buf_len = sum(len(s) for s in delta_buf)
                    if (
                        buf_len >= _TOKEN_FLUSH_CHARS
                        or _time.monotonic() - last_flush >= _TOKEN_FLUSH_INTERVAL
                    ):
                        await _flush_delta()

                tc_deltas = delta.get("tool_calls")
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.get("id") or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = tool_calls_acc[idx]
                        if tc.get("id"):
                            entry["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            entry["function"]["name"] += tc["function"]["name"]
                        if tc.get("function", {}).get("arguments"):
                            entry["function"]["arguments"] += tc["function"]["arguments"]

                if "usage" in chunk:
                    u = chunk["usage"]
                    usage_dict = {
                        "prompt": u.get("prompt_tokens", 0),
                        "completion": u.get("completion_tokens", 0),
                        "total": u.get("total_tokens", 0),
                    }

        await _flush_delta()

        tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)] if tool_calls_acc else None

        return full_content, tool_calls, usage_dict

    @staticmethod
    def _truncate_for_event(payload: Any) -> Any:
        """截断大型字符串，避免 agent_events 表存完整 HTML 等巨型内容。"""
        if isinstance(payload, str) and len(payload) > _MAX_EVENT_PAYLOAD_CHARS:
            return payload[:_MAX_EVENT_PAYLOAD_CHARS] + "...[truncated]"
        if isinstance(payload, dict):
            return {k: ChatTurnRunner._truncate_for_event(v) for k, v in payload.items()}
        if isinstance(payload, list):
            return [ChatTurnRunner._truncate_for_event(v) for v in payload]
        return payload

    async def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        results = []
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            call_id = tc.get("id", "")

            try:
                arguments = _json.loads(func.get("arguments", "{}"))
            except _json.JSONDecodeError:
                arguments = {}

            await self._publish(ChatEventType.TOOL_CALL_START, {
                "tool_name": tool_name,
                "arguments": arguments,
                "call_id": call_id,
            })

            # harness 兼容: act_start
            await self._publish_harness("act_start", {
                "tool_calls": [{"name": tool_name, "arguments": arguments}],
            })

            skill = self._find_skill(tool_name)
            if skill is None:
                error_msg = {"ok": False, "error": f"未知工具: {tool_name}"}
                await self._publish(ChatEventType.TOOL_CALL_END, {
                    "tool_name": tool_name,
                    "call_id": call_id,
                    "result": error_msg,
                    "ok": False,
                })
                await self._publish_harness("act_end", {
                    "tool_results": [{"tool_call_id": call_id, "content": f"Error: {error_msg['error']}"}],
                })
                results.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _json.dumps(error_msg, ensure_ascii=False),
                })
                continue

            try:
                ctx = SkillContext.from_dependencies(self._tool_deps)
                result = await self._executor.execute(skill, ctx, **arguments)
                ok = True
                result_content = _json.dumps(result, ensure_ascii=False, default=str)
                result_payload = result
            except Exception as exc:
                ok = False
                result_content = _json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
                result_payload = {"ok": False, "error": str(exc)}

            await self._publish(ChatEventType.TOOL_CALL_END, {
                "tool_name": tool_name,
                "call_id": call_id,
                "result": self._truncate_for_event(result_payload),
                "ok": ok,
            })

            # harness 兼容: act_end（截断后的 result_content）
            truncated_for_event = self._truncate_for_event(result_content)
            await self._publish_harness("act_end", {
                "tool_results": [{"tool_call_id": call_id, "content": truncated_for_event}],
            })

            results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_content,
            })

        return results

    def _find_skill(self, name: str) -> Optional[Skill]:
        for skill in self._tools:
            if skill.name == name and skill.is_executable:
                return skill
        registry = get_global_registry()
        for skill in registry.filter(lambda s: s.name == name and s.is_executable):
            return skill
        return None

    async def _publish(
        self, event_type: str, data: Dict[str, Any], *, persist: bool = True
    ) -> None:
        try:
            self._event_bus.publish(
                trace_id=self._trace_id,
                event_type=event_type,
                data=data,
                source=self._source,
                step=self._step,
                persist=persist,
            )
        except Exception:
            pass

    async def _publish_harness(
        self, event_type: str, data: Dict[str, Any]
    ) -> None:
        """发布 harness 兼容事件，source 统一用 self._source。"""
        try:
            self._event_bus.publish(
                trace_id=self._trace_id,
                event_type=event_type,
                data=data,
                source=self._source,
                step=self._step,
                persist=True,
            )
        except Exception:
            pass


__all__ = ["ChatTurnRunner", "ChatTurnResult"]
