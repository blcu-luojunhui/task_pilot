"""TaskInvoker：chat agent 启动业务 task 的封装依赖。

抽出来作为单独的依赖项有几个考虑：
- 让 ``run_task`` skill 不直接接触 ``TaskScheduler`` 和 ``ApiDependencies``,
  权限边界更紧；
- 未来加入审计、白名单、参数校验时，统一在这里加。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from src.infra.shared.tools import generate_task_trace_id

if TYPE_CHECKING:
    from src.api.v1.utils import ApiDependencies

logger = logging.getLogger(__name__)


class TaskInvoker:
    """启动 TaskPilot 业务任务的能力。"""

    def __init__(self, deps: "ApiDependencies") -> None:
        self._deps = deps

    async def run(
        self,
        task_name: str,
        params: Optional[Dict[str, Any]] = None,
        date_string: Optional[str] = None,
    ) -> Dict[str, Any]:
        # lazy import 打破 src.jobs <-> src.core.chat 的循环依赖
        # （src.jobs.__init__ 会触发 registered_tasks → chat.agent_task → 本模块）
        from src.jobs import TaskScheduler

        sub_trace_id = generate_task_trace_id()
        body: Dict[str, Any] = {"task_name": task_name, **(params or {})}
        if date_string:
            body["date_string"] = date_string

        scheduler = TaskScheduler(body, sub_trace_id, self._deps)
        try:
            result = await scheduler.deal()
        except Exception as exc:
            logger.exception("TaskInvoker failed to start task=%s", task_name)
            return {
                "trace_id": sub_trace_id,
                "task_name": task_name,
                "code": -1,
                "message": f"failed to start task: {exc}",
            }

        return {
            "trace_id": sub_trace_id,
            "task_name": task_name,
            "code": result.get("code"),
            "message": result.get("message"),
        }


__all__ = ["TaskInvoker"]
