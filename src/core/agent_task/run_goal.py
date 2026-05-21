"""agent.run_goal 任务：根据用户目标 + 选定工具区域执行一次 agent run。

与 chat.agent_turn 的区别：
- 不依赖 conversation / chat_messages 表
- goal 来自 task data，作为唯一的 user message
- 工具区域由前端指定，而非固定 chat_ops + task
- 结果写入 task_manager.data，不落 chat_messages
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
from src.core.chat.runner import ChatTurnRunner, ChatTurnResult
from src.core.agent_task.prompts import RUN_GOAL_SYSTEM_PROMPT
from src.jobs.task_config import TaskStatus
from src.jobs.task_handler import register

if TYPE_CHECKING:
    from src.jobs.task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)

_CANCEL_REQUESTED = 4
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

_DEFAULT_TOOL_AREAS = ["chat_ops", "task"]


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
    logger.info("RunGoal runner 使用 provider=%s model=%s", key, llm_config.model)
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

    return asyncio.create_task(
        _poll(), name=f"run-goal-cancel-poll-{scheduler.trace_id}"
    )


@register("agent.run_goal")
async def run_agent_goal(scheduler: "TaskScheduler") -> int:
    data = scheduler.data or {}
    goal = data.get("goal")
    tool_areas = data.get("tool_areas") or _DEFAULT_TOOL_AREAS

    if not goal or not isinstance(goal, str):
        await scheduler._log_task_event(
            "run_goal_invalid",
            error="goal is required and must be a non-empty string",
        )
        return TaskStatus.FAILED

    if not isinstance(tool_areas, list) or not all(isinstance(a, str) for a in tool_areas):
        await scheduler._log_task_event(
            "run_goal_invalid",
            error="tool_areas must be a list of strings",
        )
        return TaskStatus.FAILED

    logger.info(
        "RunGoal task started trace_id=%s goal=%.100s tool_areas=%s",
        scheduler.trace_id,
        goal,
        tool_areas,
    )

    # Cancel poller
    cancel_flag: Dict[str, bool] = {"requested": False, "stop": False}
    poll_task = _start_cancel_poller(scheduler, cancel_flag)

    llm_cfg = scheduler.config.llm
    events_bus = scheduler.events
    trace_id = scheduler.trace_id

    provider = _build_llm_provider(llm_cfg)

    # 加载指定工具区域
    load_agentic_tools(tool_areas)
    registry = get_global_registry()
    tools = list(registry.filter(lambda s: s.is_executable))

    if not tools:
        await scheduler._log_task_event(
            "run_goal_no_tools",
            error=f"No executable tools found for areas: {tool_areas}",
        )
        return TaskStatus.FAILED

    tool_dependencies = {
        "db": scheduler.db_client,
        "log": scheduler.log_service,
        "config": scheduler.config,
        "task_invoker": None,
    }

    # 延迟导入 TaskInvoker
    try:
        from src.core.chat.task_invoker import TaskInvoker
        from src.api.v1.utils import ApiDependencies as _ApiDeps

        api_deps = _ApiDeps(
            mysql=scheduler.db_client,
            log=scheduler.log_service,
            config=scheduler.config,
            alert=getattr(scheduler, "alert_service", None),
            lifecycle=scheduler.lifecycle,
            events=scheduler.events,
        )
        tool_dependencies["task_invoker"] = TaskInvoker(api_deps)
    except Exception:
        logger.warning("Failed to construct TaskInvoker for run_goal task")

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

    try:
        result = await runner.run(
            messages=[{"role": "user", "content": goal}],
            system_prompt=RUN_GOAL_SYSTEM_PROMPT,
        )
    except Exception:
        logger.exception("RunGoal ChatTurnRunner failed")
        if events_bus:
            try:
                events_bus.publish(
                    trace_id=trace_id,
                    event_type="chat.turn_error",
                    data={"error": "ChatTurnRunner 内部异常"},
                    source="agent",
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
        try:
            await provider.close()
        except Exception:
            pass

    # 结果写入 task_manager.data
    import json as _json

    try:
        final_data = {
            "goal": goal,
            "tool_areas": tool_areas,
            "status": result.status,
            "content": result.content,
            "token_usage": result.token_usage,
            "tool_call_results": result.tool_call_results,
        }
        await scheduler.db_client.async_save(
            "UPDATE task_manager SET data = %s WHERE trace_id = %s",
            (_json.dumps(final_data, ensure_ascii=False), trace_id),
        )
    except Exception:
        logger.exception("Failed to persist run_goal result")

    if cancel_flag["requested"]:
        return TaskStatus.CANCELLED
    if result.status == "cancelled":
        return TaskStatus.CANCELLED
    return TaskStatus.SUCCESS


__all__ = ["run_agent_goal"]
