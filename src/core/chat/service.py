"""ChatService：chat 模块门面，编排 turn 启动 / cancel 流程。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, TYPE_CHECKING

from src.core.chat.agent_task import run_chat_turn
from src.core.chat.cancel import ChatCancelRegistry

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
        account_id: int = 0,
    ):
        self._db = db
        self._log = log
        self._config = config
        self._event_bus = event_bus
        self._account_id = account_id

    async def start_turn(
        self, conversation_id: str, user_message: str, trace_id: str, deps: "ApiDependencies"
    ) -> Dict[str, Any]:
        """发起一轮 chat turn（纯文本对话）。"""
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

    async def cancel_turn(self, trace_id: str, deps: "ApiDependencies") -> bool:
        """取消指定 trace_id 的正在运行的 turn。"""
        if ChatCancelRegistry.cancel(trace_id):
            return True
        # fallback 到 task_manager 取消
        from src.jobs import TaskScheduler

        scheduler_data = {"task_name": _CHAT_TASK_NAME, "trace_id": trace_id}
        scheduler = TaskScheduler(scheduler_data, trace_id, deps, account_id=self._account_id)
        return await scheduler.cancel_task(trace_id)


__all__ = ["ChatService"]
