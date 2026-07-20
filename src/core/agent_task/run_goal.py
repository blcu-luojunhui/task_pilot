"""agent.run — 统一 Agent 执行入口（agentic / chat 双模式）。

合并原 agent.run_goal 与 chat.agent_turn，统一走 AgentLoopRunner (ReAct)。
mode="agent": 加载 tools 执行 goal，结果写入 task_manager.data
mode="chat":  空工具纯文本对话，结果写入 chat_messages
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig, LLMMessage
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider, ClaudeProvider, DeepSeekProvider,
)
from src.core.agents.capabilities.skills import get_global_registry, SkillExecutor
from src.core.agents.capabilities.tools.loader import load_agentic_tools
from src.core.agents.state.protocol import normalize_tool_calls
from src.core.agents.engine.runner import AgentLoopRunner
from src.core.agents.engine.loop import AssistantPlanner
from src.core.agents.state import AgentLoopResult
from src.core.agent_task.prompts import RUN_GOAL_SYSTEM_PROMPT
from src.core.chat.repository import ChatRepository, MSG_STATUS_COMPLETED
from src.jobs.task_config import TaskStatus
from src.jobs.task_handler import register

if TYPE_CHECKING:
    from src.jobs.task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)

_CANCEL_REQUESTED = 4
_CANCEL_POLL_INTERVAL = 2.0
_DEFAULT_TOOL_AREAS = ["chat_ops", "task"]
_HISTORY_LIMIT = 40

_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
}
_PROVIDER_DEFAULTS = {
    "openai": {"model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
    "claude": {"model": "claude-sonnet-4-6", "base_url": "https://api.anthropic.com/v1"},
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
}


def _infer_provider_key(base_url: Optional[str]) -> str:
    if not base_url:
        return "deepseek"
    bl = base_url.lower()
    if "anthropic" in bl or "claude" in bl:
        return "claude"
    if "deepseek" in bl:
        return "deepseek"
    return "openai"


def _build_llm_provider(cfg) -> LLMProvider:
    key = _infer_provider_key(cfg.base_url)
    defaults = _PROVIDER_DEFAULTS.get(key, _PROVIDER_DEFAULTS["deepseek"])
    provider_cls = _PROVIDER_MAP.get(key, DeepSeekProvider)
    llm_config = LLMConfig(
        api_key=cfg.api_key,
        model=cfg.model or defaults["model"],
        base_url=cfg.base_url or defaults["base_url"],
        temperature=cfg.temperature,
    )
    logger.info("Agent.run provider=%s model=%s", key, llm_config.model)
    return provider_cls(llm_config)


def _build_planner(provider: LLMProvider, tools: List[Any]) -> AssistantPlanner:
    """构造 planner callable，支持流式 token 回调。"""

    openai_tools: Optional[List[Dict]] = None
    if tools:
        from src.core.agents.capabilities.skills.serializer import OpenAIAdapter, ToolSpecSerializer
        serializer = ToolSpecSerializer(OpenAIAdapter())
        specs = serializer.serialize_many([t for t in tools if getattr(t, "is_executable", True)])
        openai_tools = [{"type": "function", "function": s} for s in specs]

    async def _planner(messages: List[Dict[str, Any]], step: int, **kwargs) -> Dict[str, Any]:
        llm_messages = [
            LLMMessage(
                role=m["role"], content=m.get("content", ""),
                tool_calls=m.get("tool_calls"), tool_call_id=m.get("tool_call_id"),
            )
            for m in messages
        ]

        stream_callback: Optional[Callable[[str], Any]] = kwargs.get("stream_callback")

        tools_param = openai_tools if openai_tools else None

        # 有工具时走非流式，确保 tool_calls 不丢失
        if stream_callback and provider.supports_streaming and not tools_param:
            full_content = ""
            async for token in provider.stream_chat(llm_messages, temperature=provider.config.temperature):
                full_content += token
                result = stream_callback(token)
                import inspect
                if inspect.isawaitable(result):
                    await result
            return {"role": "assistant", "content": full_content}

        # 非流式（有工具时必须走此路径以正确收集 tool_calls）
        resp = await provider.chat(
            messages=llm_messages, tools=tools_param,
            temperature=provider.config.temperature,
        )
        result: Dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        if resp.tool_calls:
            normalized = normalize_tool_calls(resp.tool_calls)
            result["tool_calls"] = [tc.to_dict() for tc in normalized]
        if resp.usage:
            result["_usage"] = {
                "prompt": resp.usage.get("prompt_tokens", 0),
                "completion": resp.usage.get("completion_tokens", 0),
                "total": resp.usage.get("total_tokens", 0),
            }
        return result

    return _planner


def _start_cancel_poller(
    scheduler: "TaskScheduler", flag: Dict[str, bool]
) -> asyncio.Task:
    async def _poll() -> None:
        try:
            while not flag["stop"]:
                try:
                    row = await scheduler.db_client.async_fetch_one(
                        "SELECT task_status FROM task_manager WHERE trace_id = %s AND account_id = %s",
                        params=(scheduler.trace_id, scheduler.account_id),
                    )
                    if row and int(row.get("task_status", 0)) == _CANCEL_REQUESTED:
                        flag["requested"] = True
                        return
                except Exception:
                    logger.debug("cancel poller transient error", exc_info=True)
                await asyncio.sleep(_CANCEL_POLL_INTERVAL)
        except asyncio.CancelledError:
            return
    return asyncio.create_task(_poll(), name=f"agent-run-cancel-{scheduler.trace_id}")


@register("agent.run")
@register("agent.run_goal")
@register("chat.agent_turn")
async def run_agent(scheduler: "TaskScheduler") -> int:
    """统一 Agent 执行入口。mode 由 task data 自动判定：
    - 有 tool_areas → agent 模式（加载 tools，执行 goal）
    - 有 conversation_id → chat 模式（空工具，纯文本对话）
    """
    data = scheduler.data or {}
    mode = data.get("mode")
    if mode not in ("agent", "chat"):
        # 自动推断
        if data.get("conversation_id"):
            mode = "chat"
        else:
            mode = "agent"

    # ── 共享初始化 ──
    cancel_flag: Dict[str, bool] = {"requested": False, "stop": False}
    poll_task = _start_cancel_poller(scheduler, cancel_flag)
    events_bus = scheduler.events
    trace_id = scheduler.trace_id
    provider = _build_llm_provider(scheduler.config.llm)

    def _cancel_checker() -> bool:
        return cancel_flag["requested"]

    # ── Agent 模式 ──
    if mode == "agent":
        return await _run_agent_mode(
            scheduler, data, provider, events_bus, trace_id, cancel_flag, poll_task, _cancel_checker,
        )

    # ── Chat 模式 ──
    return await _run_chat_mode(
        scheduler, data, provider, events_bus, trace_id, cancel_flag, poll_task, _cancel_checker,
    )


async def _run_agent_mode(
    scheduler: "TaskScheduler", data: Dict[str, Any], provider: LLMProvider,
    events_bus, trace_id: str, cancel_flag: Dict[str, bool],
    poll_task: asyncio.Task, cancel_checker: Callable[[], Any],
) -> int:
    goal = data.get("goal")
    tool_areas = data.get("tool_areas") or _DEFAULT_TOOL_AREAS
    enable_memory = bool(data.get("enable_memory", False))

    if not goal or not isinstance(goal, str):
        return TaskStatus.FAILED

    if not isinstance(tool_areas, list) or not all(isinstance(a, str) for a in tool_areas):
        return TaskStatus.FAILED

    logger.info("Agent mode trace_id=%s goal=%.100s tool_areas=%s", trace_id, goal, tool_areas)

    # 加载工具
    load_agentic_tools(tool_areas)
    registry = get_global_registry()
    tools = list(registry.filter(lambda s: s.is_executable))

    allowed_groups = data.get("allowed_tool_groups")
    exclude_tools = data.get("exclude_tools")
    if allowed_groups is not None or exclude_tools is not None:
        from src.core.agents.capabilities.tools.group_filter import filter_tools_by_groups
        tools = filter_tools_by_groups(tools, allowed_groups, exclude_tools)

    if not tools:
        logger.warning("Agent mode: no tools loaded for areas=%s", tool_areas)
        return TaskStatus.FAILED

    # 构建 planner + runner
    planner = _build_planner(provider, tools)
    executor = SkillExecutor(validate_params=False)

    tool_deps = {
        "db": scheduler.db_client, "log": scheduler.log_service,
        "config": scheduler.config, "task_invoker": None,
        "account_id": scheduler.account_id,
    }
    try:
        from src.core.chat.task_invoker import TaskInvoker
        from src.api.v1.utils import ApiDependencies as _ApiDeps
        api_deps = _ApiDeps(
            mysql=scheduler.db_client, log=scheduler.log_service,
            config=scheduler.config, alert=getattr(scheduler, "alert_service", None),
            lifecycle=scheduler.lifecycle, events=scheduler.events,
            auth=getattr(scheduler, "auth_service", None),
        )
        tool_deps["task_invoker"] = TaskInvoker(api_deps, account_id=scheduler.account_id)
    except Exception:
        logger.warning("Failed to construct TaskInvoker", exc_info=True)

    runner = AgentLoopRunner(
        planner=planner, registry=registry, executor=executor,
        max_steps=10, max_context_tokens=60000,
        is_cancelled=cancel_checker, tool_dependencies=tool_deps,
        event_bus=events_bus,
    )
    runner._goal_label = (data.get("original_goal") or goal).strip()

    # 记忆注入（通过 system 消息前缀拼接）
    injected_prompt = RUN_GOAL_SYSTEM_PROMPT
    scope_key = ""
    if enable_memory:
        from src.core.agents.capabilities.memory_store import (
            normalize_scope_key, fetch_reflections, format_memory_injection,
        )
        scope_key = normalize_scope_key(data.get("original_goal") or goal)
        try:
            reflections = await fetch_reflections(scheduler.db_client, scheduler.account_id, scope_key)
            injection = format_memory_injection(reflections)
            if injection:
                injected_prompt = f"{RUN_GOAL_SYSTEM_PROMPT}\n\n{injection}"
        except Exception:
            logger.warning("fetch reflections failed", exc_info=True)

    # 执行
    try:
        result: AgentLoopResult = await runner.run(
            goal=goal,
            messages=[
                {"role": "system", "content": injected_prompt},
                {"role": "user", "content": goal},
            ],
            trace_id=trace_id,
        )
    except Exception:
        logger.exception("AgentLoopRunner failed")
        cancel_flag["stop"] = True
        poll_task.cancel()
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED

    # 记忆写回（provider.close 之前）
    if enable_memory and scope_key:
        try:
            from src.core.agents.capabilities.memory_store import generate_reflection, save_reflection
            is_success = result.success
            reflection = await generate_reflection(provider, goal, result.final_answer or "", is_success)
            await save_reflection(scheduler.db_client, scheduler.account_id, scope_key, trace_id, reflection, is_success)
        except Exception:
            logger.warning("save reflection failed", exc_info=True)

    # 清理
    cancel_flag["stop"] = True
    poll_task.cancel()
    try:
        await poll_task
    except (asyncio.CancelledError, Exception):
        pass
    try:
        await provider.close()
    except Exception:
        pass

    # 持久化
    try:
        final_data = {
            "goal": goal, "tool_areas": tool_areas,
            "status": "completed" if result.success else "failed",
            "content": result.final_answer,
            "token_usage": result.token_usage,
        }
        await scheduler.db_client.async_save(
            "UPDATE task_manager SET data = %s WHERE trace_id = %s AND account_id = %s",
            (_json.dumps(final_data, ensure_ascii=False), trace_id, scheduler.account_id),
        )
    except Exception:
        logger.exception("Failed to persist result")

    if cancel_flag["requested"]:
        return TaskStatus.CANCELLED
    return TaskStatus.SUCCESS if result.success else TaskStatus.FAILED


async def _run_chat_mode(
    scheduler: "TaskScheduler", data: Dict[str, Any], provider: LLMProvider,
    events_bus, trace_id: str, cancel_flag: Dict[str, bool],
    poll_task: asyncio.Task, cancel_checker: Callable[[], Any],
) -> int:
    conversation_id = data.get("conversation_id")
    user_message = data.get("user_message", "")

    if not conversation_id:
        return TaskStatus.FAILED

    repo = ChatRepository(scheduler.db_client, account_id=scheduler.account_id)
    conv = await repo.get_conversation(conversation_id)
    if not conv:
        logger.warning("Chat mode: conversation not found conv_id=%s", conversation_id)
        return TaskStatus.FAILED

    # 落 user 消息
    if user_message:
        await repo.append_message(
            conversation_id=conversation_id, role="user", content=user_message, trace_id=trace_id,
        )

    # 拉历史
    llm_messages = await repo.build_llm_messages(conversation_id, limit=_HISTORY_LIMIT)

    # 构造 runner（空工具）
    registry = get_global_registry()
    planner = _build_planner(provider, [])
    executor = SkillExecutor(validate_params=False)
    runner = AgentLoopRunner(
        planner=planner, registry=registry, executor=executor,
        max_steps=1, is_cancelled=cancel_checker,
        event_bus=events_bus, chat_mode=True,
    )

    # 执行
    try:
        result: AgentLoopResult = await runner.run(
            goal=user_message or "chat",
            messages=llm_messages,
            trace_id=trace_id,
        )
    except Exception:
        logger.exception("AgentLoopRunner (chat) failed")
        cancel_flag["stop"] = True
        poll_task.cancel()
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED

    # 清理
    cancel_flag["stop"] = True
    poll_task.cancel()
    try:
        await poll_task
    except (asyncio.CancelledError, Exception):
        pass
    try:
        await provider.close()
    except Exception:
        pass

    # 持久化 assistant 回复到 chat_messages
    if result.final_answer:
        try:
            await repo.append_message(
                conversation_id=conversation_id, role="assistant",
                content=result.final_answer, trace_id=trace_id,
                token_usage=result.token_usage, status=MSG_STATUS_COMPLETED,
            )
        except Exception:
            logger.exception("Failed to persist chat assistant message")

    if cancel_flag["requested"]:
        return TaskStatus.CANCELLED
    return TaskStatus.SUCCESS if result.success else TaskStatus.FAILED


__all__ = ["run_agent"]
