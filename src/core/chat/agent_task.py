"""chat.agent_turn task：每轮用户消息 / confirm 续跑触发一次 ChatTurnRunner。

执行流程：
1. 校验 conversation_id 存在
2. 如有 user_message → 落 chat_messages
3. 拉历史消息 → 转 LLM messages
4. 起 cancel 检查（普通 chat 走 ChatCancelRegistry，升级后走 task_manager DB 轮询）
5. 构建 ChatTurnRunner → run（confirmed_tool_calls 走 confirm 续跑路径）
6. LLM 调用 escalate_to_agent 时按需创建 task_manager 记录
7. 根据 ChatTurnResult.status 落库

核心变更：
- 普通 chat 不再走 TaskScheduler / task_manager，只有 escalation 后才创建 task 记录
- run_chat_turn() 接受原始依赖而非 TaskScheduler 对象，供 send_message 端点直接调用
- @register("chat.agent_turn") 保留作为 TaskInvoker 兼容层
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider,
    ClaudeProvider,
    DeepSeekProvider,
)
from src.core.agents.capabilities.skills import get_global_registry
from src.core.agents.capabilities.tools.loader import load_agentic_tools
from src.core.chat.cancel import ChatCancelRegistry
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
    from src.infra.database import AsyncMySQLPool
    from src.infra.observability import LogService
    from src.infra.streaming import TraceEventBus
    from src.core.config import ProjectConfigSettings
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


async def _persist_runner_result(
    repo: ChatRepository,
    conversation_id: str,
    trace_id: str,
    result: ChatTurnResult,
    initial_messages_len: int,
) -> None:
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

    if result.content and result.content != "达到最大迭代次数":
        await repo.append_message(
            conversation_id=conversation_id,
            role="assistant",
            content=result.content,
            trace_id=trace_id,
            token_usage=result.token_usage,
            status=MSG_STATUS_COMPLETED,
        )


async def run_chat_turn(
    *,
    db: "AsyncMySQLPool",
    log: "LogService",
    config: "ProjectConfigSettings",
    events: "TraceEventBus",
    trace_id: str,
    account_id: int,
    conversation_id: str,
    user_message: str = "",
    confirmed_tool_calls: Optional[List[Dict]] = None,
) -> int:
    """执行一轮 chat turn。不依赖 TaskScheduler。

    普通 chat 不创建 task_manager 记录。LLM 调用 escalate_to_agent 时按需创建。

    Returns:
        TaskStatus int（SUCCESS / CANCELLED / FAILED），用于调用方判断终态。
    """
    repo = ChatRepository(db, account_id=account_id)
    conv = await repo.get_conversation(conversation_id)
    if not conv:
        log.log({"event": "chat_turn_invalid", "conversation_id": conversation_id, "error": "conversation not found"})
        return TaskStatus.FAILED

    # 1) 落 user 消息（仅普通 turn；confirm 续跑不落）
    if user_message:
        await repo.append_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            trace_id=trace_id,
        )
        if events:
            try:
                events.publish(
                    trace_id=trace_id,
                    event_type="chat.user_message",
                    data={"conversation_id": conversation_id, "content": user_message},
                    source="chat",
                )
            except Exception:
                pass

    # 2) 拉历史 → LLM messages
    llm_messages = await repo.build_llm_messages(conversation_id, limit=_HISTORY_LIMIT)
    history_baseline = len(llm_messages)

    # 3) 两阶段取消机制
    ChatCancelRegistry.register(trace_id)

    # escalated 标志：一旦 LLM 调用 escalate_to_agent，切换为 task_manager DB 轮询
    escalated: Dict[str, Any] = {"active": False, "cancel_flag": {"requested": False, "stop": False}}
    db_poll_task: Optional[asyncio.Task] = None

    async def _start_db_poller() -> asyncio.Task:
        """启动 task_manager 取消轮询（仅在 escalation 后）。"""
        flag = escalated["cancel_flag"]

        async def _poll() -> None:
            try:
                while not flag["stop"]:
                    try:
                        row = await db.async_fetch_one(
                            "SELECT task_status FROM task_manager WHERE trace_id = %s AND account_id = %s",
                            params=(trace_id, account_id),
                        )
                        if row and int(row.get("task_status", 0)) == _CANCEL_REQUESTED:
                            flag["requested"] = True
                            return
                    except Exception:
                        logger.debug("cancel poller transient error", exc_info=True)
                    await asyncio.sleep(_CANCEL_POLL_INTERVAL)
            except asyncio.CancelledError:
                return

        return asyncio.create_task(_poll(), name=f"chat-cancel-poll-{trace_id}")

    async def _upsert_task() -> None:
        """在 escalate_to_agent 时创建 task_manager 记录。"""
        try:
            await db.async_save(
                "INSERT INTO task_manager (date_string, task_name, start_timestamp, task_status, trace_id, data, account_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE task_status = VALUES(task_status)",
                params=(
                    _time.strftime("%Y-%m-%d"),
                    "chat.agent_turn",
                    int(_time.time()),
                    TaskStatus.PROCESSING,
                    trace_id,
                    _json.dumps({"conversation_id": conversation_id, "user_message": user_message}, ensure_ascii=False),
                    account_id,
                ),
            )
            logger.info("Escalated chat turn to task: trace_id=%s", trace_id)
        except Exception:
            logger.exception("Failed to upsert task_manager on escalation")

    async def _update_task_status(status: int) -> None:
        """更新 task_manager 终态（仅在 escalation 后调用）。"""
        if not escalated["active"]:
            return
        try:
            await db.async_save(
                "UPDATE task_manager SET task_status = %s, finish_timestamp = %s "
                "WHERE trace_id = %s AND account_id = %s",
                params=(status, int(_time.time()), trace_id, account_id),
            )
        except Exception:
            logger.exception("Failed to update task_manager status")

    async def on_escalate() -> None:
        """ChatTurnRunner 检测到 escalate_to_agent 时的回调。"""
        if escalated["active"]:
            return
        escalated["active"] = True
        await _upsert_task()
        nonlocal db_poll_task
        if db_poll_task is None:
            db_poll_task = await _start_db_poller()

    async def cancel_checker() -> bool:
        """组合取消检查：先查 ChatCancelRegistry，升级后也查 task_manager。"""
        if ChatCancelRegistry.is_cancelled(trace_id):
            return True
        if escalated["active"] and escalated["cancel_flag"]["requested"]:
            return True
        return False

    # 4) 构建 ChatTurnRunner
    llm_cfg = config.llm
    provider = _build_llm_provider(llm_cfg, logger)

    load_agentic_tools(["chat_ops", "task"])
    registry = get_global_registry()
    tools = list(registry.filter(lambda s: s.is_executable))

    tool_dependencies = {
        "db": db,
        "log": log,
        "config": config,
        "task_invoker": None,
        "account_id": account_id,
    }

    from src.core.chat.task_invoker import TaskInvoker
    from src.api.v1.utils import ApiDependencies as _ApiDeps

    try:
        api_deps = _ApiDeps(
            mysql=db,
            log=log,
            config=config,
            alert=None,
            lifecycle=None,
            events=events,
        )
        tool_dependencies["task_invoker"] = TaskInvoker(api_deps, account_id=account_id)
    except Exception:
        logger.warning("Failed to construct TaskInvoker for tool dependencies")

    runner = ChatTurnRunner(
        llm_provider=provider,
        tools=tools,
        trace_id=trace_id,
        event_bus=events,
        cancel_checker=cancel_checker,
        tool_dependencies=tool_dependencies,
        on_escalate=on_escalate,
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
        if events:
            try:
                events.publish(
                    trace_id=trace_id,
                    event_type="chat.turn_error",
                    data={"error": "ChatTurnRunner 内部异常"},
                    source="chat",
                )
            except Exception:
                pass
        _cleanup_cancel(escalated, db_poll_task, trace_id)
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED
    finally:
        _cleanup_cancel(escalated, db_poll_task, trace_id)
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

    # 7) 终态映射 + 更新 task_manager（仅在升级后）
    if ChatCancelRegistry.is_cancelled(trace_id) or escalated["cancel_flag"]["requested"]:
        final_status = TaskStatus.CANCELLED
    elif result.status == "cancelled":
        final_status = TaskStatus.CANCELLED
    else:
        final_status = TaskStatus.SUCCESS

    await _update_task_status(final_status)
    return final_status


def _cleanup_cancel(
    escalated: Dict[str, Any],
    db_poll_task: Optional[asyncio.Task],
    trace_id: str,
) -> None:
    escalated["cancel_flag"]["stop"] = True
    if db_poll_task:
        db_poll_task.cancel()
    ChatCancelRegistry.deregister(trace_id)


# ── 注册 handler（兼容 TaskInvoker 通过 TaskScheduler 启动的 chat 子任务）──

@register("chat.agent_turn")
async def chat_agent_turn(scheduler: "TaskScheduler") -> int:
    """TaskScheduler 兼容层：提取 scheduler 属性后委托给 run_chat_turn。"""
    data = scheduler.data or {}
    conversation_id = data.get("conversation_id")
    user_message = data.get("user_message", "")
    confirmed_tool_calls = data.get("confirmed_tool_calls")

    if not conversation_id:
        return TaskStatus.FAILED

    return await run_chat_turn(
        db=scheduler.db_client,
        log=scheduler.log_service,
        config=scheduler.config,
        events=scheduler.events,
        trace_id=scheduler.trace_id,
        account_id=scheduler.account_id,
        conversation_id=conversation_id,
        user_message=user_message,
        confirmed_tool_calls=confirmed_tool_calls,
    )


__all__ = ["run_chat_turn", "chat_agent_turn"]
