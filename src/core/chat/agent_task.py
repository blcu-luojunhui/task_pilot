"""chat.agent_turn task：每轮用户消息 / confirm 续跑触发一次 ChatTurnRunner。

执行流程：
1. 校验 conversation_id 存在
2. 如有 user_message → 落 chat_messages
3. 拉历史消息 → 转 LLM messages
4. 起 cancel poller
5. 构建 ChatTurnRunner → run（confirmed_tool_calls 走 confirm 续跑路径）
6. 根据 ChatTurnResult.status 落库
7. 返回 SUCCESS / CANCELLED / FAILED

与旧实现的区别：不再导入 Agent / AgentLoopRunner / AgentLoopHarness，
改为轻量 ChatTurnRunner，直接复用 LLMProvider / ToolSpecSerializer / TraceEventBus。
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider,
    ClaudeProvider,
    DeepSeekProvider,
)
from src.core.agents.capabilities.skills import get_global_registry
from src.core.agents.capabilities.tools.loader import load_agentic_tools
from src.core.chat.repository import (
    ChatRepository,
    MSG_STATUS_COMPLETED,
    MSG_STATUS_PENDING_CONFIRMATION,
    MSG_STATUS_CANCELLED,
)
from src.core.chat.runner import ChatTurnRunner, ChatTurnResult
from src.core.chat.prompts import CHAT_SYSTEM_PROMPT
from src.jobs.task_config import TaskStatus
from src.jobs.task_handler import register

if TYPE_CHECKING:
    from src.jobs.task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)

_CANCEL_REQUESTED = 4
_HISTORY_LIMIT = 40
_CANCEL_POLL_INTERVAL = 2.0

_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
}

_PROVIDER_DEFAULTS = {
    "openai": {"model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
    "claude": {
        "model": "claude-sonnet-4-6",
        "base_url": "https://api.anthropic.com/v1",
    },
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


def _build_llm_provider(cfg, logger_inst) -> LLMProvider:
    key = _infer_provider_key(cfg.base_url)
    defaults = _PROVIDER_DEFAULTS.get(key, _PROVIDER_DEFAULTS["deepseek"])
    provider_cls = _PROVIDER_MAP.get(key, DeepSeekProvider)
    llm_config = LLMConfig(
        api_key=cfg.api_key,
        model=cfg.model or defaults["model"],
        base_url=cfg.base_url or defaults["base_url"],
        temperature=cfg.temperature,
    )
    logger_inst.info("ChatTurnRunner 使用 provider=%s model=%s", key, llm_config.model)
    return provider_cls(llm_config)


def _start_cancel_poller(
    scheduler: "TaskScheduler", flag: Dict[str, bool]
) -> asyncio.Task:
    async def _poll() -> None:
        try:
            while not flag["stop"]:
                try:
                    row = await scheduler.db_client.async_fetch_one(
                        "SELECT task_status FROM task_manager WHERE trace_id = %s",
                        params=(scheduler.trace_id,),
                    )
                    if row and int(row.get("task_status", 0)) == _CANCEL_REQUESTED:
                        flag["requested"] = True
                        return
                except Exception:
                    logger.debug("cancel poller transient error", exc_info=True)
                await asyncio.sleep(_CANCEL_POLL_INTERVAL)
        except asyncio.CancelledError:
            return

    return asyncio.create_task(_poll(), name=f"chat-cancel-poll-{scheduler.trace_id}")


async def _persist_runner_result(
    repo: ChatRepository,
    conversation_id: str,
    trace_id: str,
    result: ChatTurnResult,
    initial_messages_len: int,
) -> None:
    """根据 ChatTurnResult 落库 assistant / tool 消息。

    pending_confirmation → status=1 + tool_calls 写入消息
    completed/cancelled → 正常落库
    """
    if result.status == "pending_confirmation":
        await repo.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=result.content,
            tool_calls=result.proposed_tool_calls,
            trace_id=trace_id,
            token_usage=result.token_usage,
            status=MSG_STATUS_PENDING_CONFIRMATION,
        )
        return

    if result.status == "cancelled":
        if result.content:
            await repo.append_message(
                conversation_id=conversation_id,
                role="assistant",
                content=result.content,
                trace_id=trace_id,
                token_usage=result.token_usage,
                status=MSG_STATUS_CANCELLED,
            )
        return

    # completed: LLM 返回了纯文本（无 tool_calls），落 assistant 消息
    if result.content and result.content != "达到最大迭代次数":
        await repo.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=result.content,
            trace_id=trace_id,
            token_usage=result.token_usage,
            status=MSG_STATUS_COMPLETED,
        )


@register("chat.agent_turn")
async def chat_agent_turn(scheduler: "TaskScheduler") -> int:
    data = scheduler.data or {}
    conversation_id = data.get("conversation_id")
    user_message = data.get("user_message")
    confirmed_tool_calls = data.get("confirmed_tool_calls")

    if not conversation_id:
        await scheduler._log_task_event(
            "chat_turn_invalid",
            error="missing conversation_id",
        )
        return TaskStatus.FAILED

    repo = ChatRepository(scheduler.db_client)
    conv = await repo.get_conversation(conversation_id)
    if not conv:
        await scheduler._log_task_event(
            "chat_turn_invalid",
            conversation_id=conversation_id,
            error="conversation not found",
        )
        return TaskStatus.FAILED

    # 1) 落 user 消息（仅普通 turn；confirm 续跑不落）
    if user_message:
        await repo.append_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            trace_id=scheduler.trace_id,
        )
        scheduler._publish_event(
            "chat.user_message",
            {"conversation_id": conversation_id, "content": user_message},
        )

    # 2) 拉历史 → LLM messages
    if confirmed_tool_calls:
        # confirm 续跑：需要包含 pending 消息本身（已变更为 completed），用 repo.build_llm_messages
        llm_messages = await repo.build_llm_messages(conversation_id, limit=_HISTORY_LIMIT)
    else:
        # 普通 turn：pending 消息会被过滤，其他正常组装
        llm_messages = await repo.build_llm_messages(conversation_id, limit=_HISTORY_LIMIT)

    history_baseline = len(llm_messages)

    # 3) Cancel poller
    cancel_flag: Dict[str, bool] = {"requested": False, "stop": False}
    poll_task = _start_cancel_poller(scheduler, cancel_flag)

    # 4) 构建 ChatTurnRunner
    llm_cfg = scheduler.config.llm
    events_bus = scheduler.events
    trace_id = scheduler.trace_id

    provider = _build_llm_provider(llm_cfg, logger)

    # 加载工具区域
    load_agentic_tools(["chat_ops", "task"])
    registry = get_global_registry()
    tools = list(registry.filter(lambda s: s.is_executable))

    tool_dependencies = {
        "db": scheduler.db_client,
        "log": scheduler.log_service,
        "config": scheduler.config,
        "task_invoker": None,  # 由 chat_ops 的 run_task 使用，通过 MappingResolver 按需解析
    }
    # 延迟导入 TaskInvoker 避免循环
    from src.core.chat.task_invoker import TaskInvoker
    from src.api.v1.utils import ApiDependencies as _ApiDeps
    try:
        api_deps = _ApiDeps(
            mysql=scheduler.db_client,
            log=scheduler.log_service,
            config=scheduler.config,
            alert=getattr(scheduler, "alert_service", None),
            lifecycle=scheduler.lifecycle,
            events=scheduler.events,
        )
        task_invoker = TaskInvoker(api_deps)
        tool_dependencies["task_invoker"] = task_invoker
    except Exception:
        logger.warning("Failed to construct TaskInvoker for tool dependencies")

    async def cancel_checker() -> bool:
        return cancel_flag["requested"]

    runner = ChatTurnRunner(
        llm_provider=provider,
        tools=tools,
        trace_id=trace_id,
        event_bus=events_bus,
        cancel_checker=cancel_checker,
        tool_dependencies=tool_dependencies,
    )

    # 5) 运行
    try:
        result = await runner.run(
            messages=llm_messages,
            system_prompt=CHAT_SYSTEM_PROMPT,
            confirmed_tool_calls=confirmed_tool_calls,
        )
    except Exception:
        logger.exception("ChatTurnRunner failed")
        await scheduler._log_task_event(
            "chat_turn_error",
            trace_id=trace_id,
            error="runner exception",
        )
        if events_bus:
            try:
                events_bus.publish(
                    trace_id=trace_id,
                    event_type="chat.turn_error",
                    data={"error": "ChatTurnRunner 内部异常"},
                    source="chat",
                )
            except Exception:
                pass
        cancel_flag["stop"] = True
        poll_task.cancel()
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED
    finally:
        cancel_flag["stop"] = True
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass
        # 关闭 provider 内部持有的 aiohttp ClientSession，避免 Unclosed session 警告
        try:
            await provider.close()
        except Exception:
            pass

    # 6) 落库
    try:
        await _persist_runner_result(
            repo,
            conversation_id=conversation_id,
            trace_id=trace_id,
            result=result,
            initial_messages_len=history_baseline,
        )
    except Exception:
        logger.exception("Failed to persist runner result")

    # 7) 终态映射
    if cancel_flag["requested"]:
        return TaskStatus.CANCELLED
    if result.status == "cancelled":
        return TaskStatus.CANCELLED
    return TaskStatus.SUCCESS


__all__ = ["chat_agent_turn"]
