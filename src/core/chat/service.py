"""ChatService：chat 模块门面，编排 turn 启动 / confirm / cancel 流程。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from src.core.chat.agent_task import run_chat_turn
from src.core.chat.cancel import ChatCancelRegistry
from src.core.chat.repository import (
    ChatRepository,
    MSG_STATUS_COMPLETED,
    MSG_STATUS_REJECTED,
)

if TYPE_CHECKING:
    from src.infra.database import AsyncMySQLPool
    from src.infra.observability import LogService
    from src.infra.streaming import TraceEventBus
    from src.core.config import ProjectConfigSettings
    from src.api.v1.utils import ApiDependencies

logger = logging.getLogger(__name__)

_CHAT_TASK_NAME = "chat.agent_turn"


class ChatService:
    def __init__(
        self,
        db: "AsyncMySQLPool",
        log: "LogService",
        config: "ProjectConfigSettings",
        event_bus: "TraceEventBus",
        task_invoker_loader=None,
        account_id: int = 0,
    ):
        self._db = db
        self._log = log
        self._config = config
        self._event_bus = event_bus
        self._task_invoker_loader = task_invoker_loader
        self._account_id = account_id

    def _repo(self) -> ChatRepository:
        return ChatRepository(self._db, account_id=self._account_id)

    async def start_turn(
        self, conversation_id: str, user_message: str, trace_id: str, deps: "ApiDependencies"
    ) -> Dict[str, Any]:
        """发起一轮 chat turn（轻量，不创建 task_manager 记录）。"""
        asyncio.create_task(
            run_chat_turn(
                db=self._db,
                log=self._log,
                config=self._config,
                events=self._event_bus,
                trace_id=trace_id,
                account_id=self._account_id,
                conversation_id=conversation_id,
                user_message=user_message,
            ),
            name=f"chat-turn-{trace_id}",
        )
        return {
            "code": 0,
            "data": {
                "code": 0,
                "message": "chat turn started",
                "trace_id": trace_id,
            },
        }

    async def confirm_plan(
        self,
        conversation_id: str,
        message_id: int,
        action: str,
        trace_id: str,
        deps: "ApiDependencies",
    ) -> Optional[str]:
        """处理用户确认/拒绝。

        Returns:
            新 trace_id（confirm 时）或 None（reject 时或找不到 pending 消息）
        """
        repo = self._repo()
        pending = await repo.get_pending_message(conversation_id)

        if not pending or int(pending.get("id", 0)) != message_id:
            return "__not_found__"

        if action == "reject":
            await repo.update_message_status(message_id, MSG_STATUS_REJECTED)
            await repo.append_message(
                conversation_id=conversation_id,
                role="assistant",
                content="好的，已取消该操作。",
                trace_id=trace_id,
                status=MSG_STATUS_COMPLETED,
            )
            await self._log.log({
                "event": "chat_plan_rejected",
                "conversation_id": conversation_id,
                "message_id": message_id,
            })
            return None

        # action == "confirm"
        tool_calls = pending.get("tool_calls")
        if not tool_calls:
            return None

        await repo.update_message_status(message_id, MSG_STATUS_COMPLETED)

        try:
            self._event_bus.ensure_trace(trace_id, metadata={"task_name": _CHAT_TASK_NAME, "account_id": self._account_id})
        except Exception:
            pass

        # 续跑 chat turn（confirm 时已在 agentic 模式，escalation 已触发 task 创建）
        asyncio.create_task(
            run_chat_turn(
                db=self._db,
                log=self._log,
                config=self._config,
                events=self._event_bus,
                trace_id=trace_id,
                account_id=self._account_id,
                conversation_id=conversation_id,
                user_message="",
                confirmed_tool_calls=tool_calls,
            ),
            name=f"chat-confirm-{trace_id}",
        )

        await self._log.log({
            "event": "chat_plan_confirmed",
            "conversation_id": conversation_id,
            "message_id": message_id,
            "new_trace_id": trace_id,
        })
        return trace_id

    async def cancel_turn(self, trace_id: str, deps: "ApiDependencies") -> bool:
        """取消指定 trace_id 的正在运行的 turn。"""
        # 优先轻量取消
        if ChatCancelRegistry.cancel(trace_id):
            return True
        # fallback 到 task_manager 取消
        from src.jobs import TaskScheduler

        scheduler_data = {"task_name": _CHAT_TASK_NAME, "trace_id": trace_id}
        scheduler = TaskScheduler(scheduler_data, trace_id, deps, account_id=self._account_id)
        return await scheduler.cancel_task(trace_id)


__all__ = ["ChatService"]
