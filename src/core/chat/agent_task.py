"""chat.agent_turn task：每轮用户消息触发一次 ChatTurnRunner。

执行流程：
1. 校验 conversation_id 存在
2. 如有 user_message → 落 chat_messages
3. 拉历史消息 → 转 LLM messages
4. 起 cancel 检查（ChatCancelRegistry）
5. 构建 ChatTurnRunner（空工具列表，纯文本对话）→ run
6. 根据 ChatTurnResult.status 落库

纯对话模式，不创建 task_manager 记录，不支持 escalation。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider,
    ClaudeProvider,
    DeepSeekProvider,
)
from src.core.chat.cancel import ChatCancelRegistry
from src.core.chat.repository import (
    ChatRepository,
    MSG_STATUS_COMPLETED,
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

_HISTORY_LIMIT = 40

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
) -> None:
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
) -> int:
    """执行一轮 chat turn。纯文本对话，不创建 task_manager 记录。

    Returns:
        TaskStatus int（SUCCESS / CANCELLED / FAILED）。
    """
    repo = ChatRepository(db, account_id=account_id)
    conv = await repo.get_conversation(conversation_id)
    if not conv:
        log.log({"event": "chat_turn_invalid", "conversation_id": conversation_id, "error": "conversation not found"})
        return TaskStatus.FAILED

    # 1) 落 user 消息
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

    # 3) 取消机制（ChatCancelRegistry 单阶段）
    ChatCancelRegistry.register(trace_id)

    async def cancel_checker() -> bool:
        return ChatCancelRegistry.is_cancelled(trace_id)

    # 4) 构建 ChatTurnRunner（空工具列表 = 纯文本对话）
    llm_cfg = config.llm
    provider = _build_llm_provider(llm_cfg, logger)

    runner = ChatTurnRunner(
        llm_provider=provider,
        tools=[],  # 纯文本对话，不暴露任何工具
        trace_id=trace_id,
        event_bus=events,
        cancel_checker=cancel_checker,
    )

    # 5) 运行
    try:
        result = await runner.run(
            messages=llm_messages,
            system_prompt=CHAT_SYSTEM_PROMPT,
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
        ChatCancelRegistry.deregister(trace_id)
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED
    finally:
        ChatCancelRegistry.deregister(trace_id)
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
        )
    except Exception:
        logger.exception("Failed to persist runner result")

    # 7) 终态映射
    if ChatCancelRegistry.is_cancelled(trace_id):
        return TaskStatus.CANCELLED
    elif result.status == "cancelled":
        return TaskStatus.CANCELLED
    else:
        return TaskStatus.SUCCESS


# ── 注册 handler（兼容 TaskInvoker 通过 TaskScheduler 启动的 chat 子任务）──

@register("chat.agent_turn")
async def chat_agent_turn(scheduler: "TaskScheduler") -> int:
    """TaskScheduler 兼容层：提取 scheduler 属性后委托给 run_chat_turn。"""
    data = scheduler.data or {}
    conversation_id = data.get("conversation_id")
    user_message = data.get("user_message", "")

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
    )


__all__ = ["run_chat_turn", "chat_agent_turn"]
