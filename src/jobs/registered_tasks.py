"""已注册的任务处理器——通过 @register 装饰器自动注册到全局 registry。"""
from __future__ import annotations

import json
import logging

from src.jobs.task_config import TaskStatus
from src.jobs.task_handler import register

logger = logging.getLogger(__name__)


@register("test_echo")
async def test_echo(scheduler) -> int:
    """简单的 echo 测试任务：写入 data 后返回 SUCCESS。"""
    await scheduler._log_task_event("task_started", message="Hello from test_echo!")
    await scheduler.db_client.async_save(
        "UPDATE task_manager SET data = %s WHERE trace_id = %s",
        (json.dumps({"status": "ok", "message": "Echo task completed"}), scheduler.trace_id),
    )
    return TaskStatus.SUCCESS


@register("test_fail")
async def test_fail(scheduler) -> int:
    """必定失败的任务，用于验证 error 摘要和 recent_failures。"""
    await scheduler.db_client.async_save(
        "UPDATE task_manager SET data = %s WHERE trace_id = %s",
        (json.dumps({
            "error": "Intentional failure for testing error summary display",
            "error_message": "DB connection timeout after 30s retry",
            "step": "fetch_user_data",
        }), scheduler.trace_id),
    )
    raise RuntimeError("Intentional task failure — testing error summary")
