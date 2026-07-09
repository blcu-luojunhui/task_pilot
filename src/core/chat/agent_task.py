"""agent_task：chat turn 执行入口，委托给 AgentLoopRunner (ReAct)。

run_chat_turn() 被 API 端点直接调用（不经过 TaskScheduler），
chat.agent_turn 统一注册在 run_goal.py 中。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider, ClaudeProvider, DeepSeekProvider,
)
from src.core.agents.capabilities.skills import get_global_registry, SkillExecutor
from src.core.agents.engine.runner import AgentLoopRunner
from src.core.agents.state import AgentLoopResult
from src.core.chat.repository import ChatRepository, MSG_STATUS_COMPLETED
from src.jobs.task_config import TaskStatus
from src.core.agents.capabilities.llm.base import LLMMessage
from src.core.agents.engine.loop import AssistantPlanner
from typing import Any, Dict, List

if TYPE_CHECKING:
    from src.infra.database import AsyncMySQLPool
    from src.infra.observability import LogService
    from src.infra.streaming import TraceEventBus
    from src.core.config import ProjectConfigSettings

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 40

_PROVIDER_MAP = {"openai": OpenAIProvider, "claude": ClaudeProvider, "deepseek": DeepSeekProvider}
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


def _make_provider(cfg, logger_inst) -> LLMProvider:
    key = _infer_provider_key(cfg.base_url)
    defaults = _PROVIDER_DEFAULTS.get(key, _PROVIDER_DEFAULTS["deepseek"])
    provider_cls = _PROVIDER_MAP.get(key, DeepSeekProvider)
    llm_config = LLMConfig(
        api_key=cfg.api_key, model=cfg.model or defaults["model"],
        base_url=cfg.base_url or defaults["base_url"], temperature=cfg.temperature,
    )
    logger_inst.info("ChatTurn provider=%s model=%s", key, llm_config.model)
    return provider_cls(llm_config)


def _build_planner(provider: LLMProvider, tools: List[Any]) -> AssistantPlanner:
    """构造 planner callable（空工具 = 纯文本对话）。"""
    async def _planner(messages: List[Dict[str, Any]], step: int, **kwargs) -> Dict[str, Any]:
        llm_messages = [
            LLMMessage(role=m["role"], content=m.get("content", ""),
                       tool_calls=m.get("tool_calls"), tool_call_id=m.get("tool_call_id"))
            for m in messages
        ]
        stream_callback = kwargs.get("stream_callback")
        if stream_callback and provider.supports_streaming:
            full_content = ""
            async for token in provider.stream_chat(llm_messages, temperature=provider.config.temperature):
                full_content += token
                result = stream_callback(token)
                import inspect
                if inspect.isawaitable(result):
                    await result
            return {"role": "assistant", "content": full_content}

        resp = await provider.chat(
            messages=llm_messages, tools=None, temperature=provider.config.temperature)
        result: Dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        if resp.usage:
            result["_usage"] = {k: resp.usage.get(f"{k}_tokens", 0) for k in ("prompt", "completion", "total")}
        return result
    return _planner


async def run_chat_turn(
    *, db: "AsyncMySQLPool", log: "LogService", config: "ProjectConfigSettings",
    events: "TraceEventBus", trace_id: str, account_id: int,
    conversation_id: str, user_message: str = "",
) -> int:
    """执行一轮 chat turn（API 端点直接调用，纯文本对话）。"""
    repo = ChatRepository(db, account_id=account_id)
    conv = await repo.get_conversation(conversation_id)
    if not conv:
        log.log({"event": "chat_turn_invalid", "conversation_id": conversation_id})
        return TaskStatus.FAILED

    if user_message:
        await repo.append_message(
            conversation_id=conversation_id, role="user", content=user_message, trace_id=trace_id)

    llm_messages = await repo.build_llm_messages(conversation_id, limit=_HISTORY_LIMIT)

    provider = _make_provider(config.llm, logger)
    registry = get_global_registry()
    planner = _build_planner(provider, [])  # 空工具 = 纯文本
    executor = SkillExecutor(validate_params=False)

    runner = AgentLoopRunner(
        planner=planner, registry=registry, executor=executor,
        max_steps=1, chat_mode=True, event_bus=events,
    )

    try:
        result: AgentLoopResult = await runner.run(
            goal=user_message or "chat", messages=llm_messages, trace_id=trace_id)
    except Exception:
        logger.exception("ChatRunner failed")
        try:
            await provider.close()
        except Exception:
            pass
        return TaskStatus.FAILED

    try:
        await provider.close()
    except Exception:
        pass

    if result.final_answer:
        try:
            await repo.append_message(
                conversation_id=conversation_id, role="assistant",
                content=result.final_answer, trace_id=trace_id,
                token_usage=result.token_usage, status=MSG_STATUS_COMPLETED,
            )
        except Exception:
            logger.exception("Failed to persist chat message")

    return TaskStatus.SUCCESS if result.success else TaskStatus.FAILED


# 旧的 task handler 注册已统一在 run_goal.py 中（@register("chat.agent_turn")）

__all__ = ["run_chat_turn"]
