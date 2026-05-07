import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from src.infra.shared import TaskScheduleResponse, ErrorCode
from src.jobs.task_handler import TaskHandler
from src.jobs.task_config import (
    TaskStatus,
    TaskConstants,
    get_task_config,
)
from src.jobs.task_utils import (
    TaskError,
    TaskValidationError,
    TaskConcurrencyError,
    TaskUtils,
)
from src.infra.observability import metrics

if TYPE_CHECKING:
    from src.api.v1.utils import ApiDependencies

logger = logging.getLogger(__name__)


class TaskScheduler(TaskHandler):
    """
    统一任务调度器

    使用方法：
        scheduler = TaskScheduler(data, trace_id, deps)
        result = await scheduler.deal()
    """

    def __init__(
        self,
        data: dict,
        trace_id: str,
        deps: "ApiDependencies",
    ):
        super().__init__(data, trace_id, deps.log, deps.db, deps.config)
        self.table = TaskUtils.validate_table_name(
            deps.config.task_table or TaskConstants.TASK_TABLE
        )
        self.alert_service = deps.alert
        self.lifecycle = deps.lifecycle
        self.events = getattr(deps, "events", None)

    async def _send_alert(self, title: str, detail: dict, dedup_key: str = None):
        if self.alert_service:
            await self.alert_service.send_alert(
                title=title,
                detail=detail,
                dedup_key=dedup_key,
            )

    def _publish_event(self, event_type: str, data: dict, step: Optional[int] = None):
        if self.events:
            self.events.publish(
                trace_id=self.trace_id,
                event_type=event_type,
                data=data,
                source="task_scheduler",
                step=step,
            )

    # ==================== 数据库操作 ====================

    async def _insert_or_ignore_task(self, task_name: str, date_str: str) -> None:
        query = f"""
            INSERT IGNORE INTO {self.table}
            (date_string, task_name, start_timestamp, task_status, trace_id, data)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        await self.db_client.async_save(
            query=query,
            params=(
                date_str,
                task_name,
                int(time.time()),
                TaskStatus.INIT,
                self.trace_id,
                json.dumps(self.data, ensure_ascii=False),
            ),
        )

    async def _try_lock_task(self) -> bool:
        query = f"""
            UPDATE {self.table}
            SET task_status = %s
            WHERE trace_id = %s AND task_status = %s
        """
        result = await self.db_client.async_save(
            query=query,
            params=(TaskStatus.PROCESSING, self.trace_id, TaskStatus.INIT),
        )
        return bool(result)

    async def _release_task(self, status: int) -> None:
        query = f"""
            UPDATE {self.table}
            SET task_status = %s, finish_timestamp = %s
            WHERE trace_id = %s AND task_status IN (%s, %s)
        """
        await self.db_client.async_save(
            query=query,
            params=(
                status,
                int(time.time()),
                self.trace_id,
                TaskStatus.PROCESSING,
                TaskStatus.CANCEL_REQUESTED,
            ),
        )

    async def _get_processing_tasks(self, task_name: str) -> List[Dict[str, Any]]:
        query = f"""
            SELECT trace_id, start_timestamp, data
            FROM {self.table}
            WHERE task_status = %s AND task_name = %s
        """
        rows = await self.db_client.async_fetch(
            query=query,
            params=(TaskStatus.PROCESSING, task_name),
        )
        return rows or []

    # ==================== 任务检查 ====================

    async def _check_task_concurrency_and_timeout(self, task_name: str) -> None:
        processing_tasks = await self._get_processing_tasks(task_name)

        if not processing_tasks:
            return

        config = get_task_config(task_name)
        current_time = int(time.time())

        timeout_tasks = [
            task
            for task in processing_tasks
            if current_time - task["start_timestamp"] > config.timeout
        ]

        if timeout_tasks:
            await self._log_task_event(
                "task_timeout_detected",
                task_name=task_name,
                timeout_count=len(timeout_tasks),
                timeout_tasks=[t["trace_id"] for t in timeout_tasks],
            )

            await self._send_alert(
                title=f"Task Timeout Alert: {task_name}",
                detail={
                    "task_name": task_name,
                    "timeout_count": len(timeout_tasks),
                    "timeout_threshold": config.timeout,
                    "timeout_tasks": [
                        {
                            "trace_id": t["trace_id"],
                            "running_time": current_time - t["start_timestamp"],
                        }
                        for t in timeout_tasks
                    ],
                },
                dedup_key=f"timeout_{task_name}",
            )

            for task in timeout_tasks:
                await self._force_release_task(task["trace_id"], TaskStatus.FAILED)

        active_tasks = [
            task
            for task in processing_tasks
            if current_time - task["start_timestamp"] <= config.timeout
        ]

        if len(active_tasks) >= config.max_concurrent:
            await self._log_task_event(
                "task_concurrency_limit",
                task_name=task_name,
                current_count=len(active_tasks),
                max_concurrent=config.max_concurrent,
            )

            await self._send_alert(
                title=f"Task Concurrency Limit: {task_name}",
                detail={
                    "task_name": task_name,
                    "current_count": len(active_tasks),
                    "max_concurrent": config.max_concurrent,
                    "active_tasks": [t["trace_id"] for t in active_tasks],
                },
                dedup_key=f"concurrency_{task_name}",
            )

            raise TaskConcurrencyError(
                f"Task {task_name} has reached max concurrency limit "
                f"({len(active_tasks)}/{config.max_concurrent})",
                task_name=task_name,
            )

    # ==================== 任务执行 ====================

    async def _run_with_guard(
        self,
        task_name: str,
        date_str: str,
        task_handler,
    ) -> dict:
        try:
            await self._check_task_concurrency_and_timeout(task_name)
        except TaskConcurrencyError as e:
            return TaskScheduleResponse.fail_response(ErrorCode.CONCURRENCY_LIMIT, str(e))

        await self._insert_or_ignore_task(task_name, date_str)

        if not await self._try_lock_task():
            return TaskScheduleResponse.fail_response(
                ErrorCode.TASK_ALREADY_PROCESSING, "Task is already processing"
            )

        self._publish_event(
            "task.accepted",
            {"task_name": task_name},
        )

        async def _task_wrapper():
            status = TaskStatus.FAILED
            config = get_task_config(task_name)
            start_time = time.time()
            self._publish_event(
                "task.started",
                {"task_name": task_name},
            )

            try:
                await self._log_task_event("task_started", task_name=task_name)
                status = await task_handler()

                duration = time.time() - start_time
                await self._log_task_event(
                    "task_completed",
                    task_name=task_name,
                    status=status,
                    duration=duration,
                )

                # 记录成功完成的任务
                status_label = "success" if status == TaskStatus.SUCCESS else "failed"
                metrics.tasks_completed_total.labels(
                    task_name=task_name,
                    status=status_label,
                ).inc()

            except TaskError as e:
                duration = time.time() - start_time
                error_detail = TaskUtils.format_error_detail(e)

                await self._log_task_event(
                    "task_failed",
                    task_name=task_name,
                    error=error_detail,
                    duration=duration,
                )

                metrics.tasks_completed_total.labels(
                    task_name=task_name,
                    status="failed",
                ).inc()

                if config.alert_on_failure:
                    await self._send_alert(
                        title=f"Task Failed: {task_name}",
                        detail={
                            "task_name": task_name,
                            "trace_id": self.trace_id,
                            "error": error_detail,
                            "duration": duration,
                            "retryable": e.retryable,
                        },
                        dedup_key=f"task_failed_{task_name}_{self.trace_id}",
                    )

            except asyncio.CancelledError:
                status = TaskStatus.CANCELLED
                duration = time.time() - start_time
                await self._log_task_event(
                    "task_cancelled",
                    task_name=task_name,
                    duration=duration,
                )
                metrics.tasks_completed_total.labels(
                    task_name=task_name,
                    status="cancelled",
                ).inc()
                raise

            except Exception as e:
                duration = time.time() - start_time
                error_detail = TaskUtils.format_error_detail(e)

                await self._log_task_event(
                    "task_error",
                    task_name=task_name,
                    error=error_detail,
                    duration=duration,
                )

                metrics.tasks_completed_total.labels(
                    task_name=task_name,
                    status="error",
                ).inc()

                await self._send_alert(
                    title=f"Task Error: {task_name}",
                    detail={
                        "task_name": task_name,
                        "trace_id": self.trace_id,
                        "error": error_detail,
                        "duration": duration,
                    },
                    dedup_key=f"task_error_{task_name}_{self.trace_id}",
                )

            finally:
                await self._release_task(status)
                if self.lifecycle:
                    await self.lifecycle.unregister(self.trace_id)
                self._publish_event(
                    "task.finished",
                    {
                        "task_name": task_name,
                        "status": str(status),
                        "duration_seconds": time.time() - start_time,
                    },
                )
                if self.events:
                    self.events.close_trace(self.trace_id)

        task = asyncio.create_task(_task_wrapper(), name=f"{task_name}_{self.trace_id}")
        metrics.tasks_started_total.labels(task_name=task_name).inc()
        if self.lifecycle:
            await self.lifecycle.register(self.trace_id, task)

        return TaskScheduleResponse.success_response(
            task_name=task_name,
            data={
                "code": 0,
                "message": "Task started successfully",
                "trace_id": self.trace_id,
            },
        )

    # ==================== 任务管理接口 ====================

    async def get_task_status(self, trace_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        trace_id = trace_id or self.trace_id
        query = f"SELECT * FROM {self.table} WHERE trace_id = %s"
        return await self.db_client.async_fetch_one(query, params=(trace_id,))

    async def cancel_task(self, trace_id: Optional[str] = None) -> bool:
        trace_id = trace_id or self.trace_id
        query = f"""
            UPDATE {self.table}
            SET task_status = CASE
                    WHEN task_status = %s THEN %s
                    WHEN task_status = %s THEN %s
                END,
                finish_timestamp = CASE
                    WHEN task_status = %s THEN %s
                    ELSE finish_timestamp
                END
            WHERE trace_id = %s AND task_status IN (%s, %s)
        """
        result = await self.db_client.async_save(
            query,
            (
                TaskStatus.INIT,
                TaskStatus.CANCELLED,
                TaskStatus.PROCESSING,
                TaskStatus.CANCEL_REQUESTED,
                TaskStatus.INIT,
                int(time.time()),
                trace_id,
                TaskStatus.INIT,
                TaskStatus.PROCESSING,
            ),
        )

        if result:
            await self._log_task_event("task_cancel_requested", trace_id=trace_id)
            self._publish_event(
                "task.cancel_requested",
                {"trace_id": trace_id},
            )

        return bool(result)

    async def _force_release_task(self, trace_id: str, status: int) -> None:
        query = f"""
            UPDATE {self.table}
            SET task_status = %s, finish_timestamp = %s
            WHERE trace_id = %s
        """
        await self.db_client.async_save(
            query,
            (status, int(time.time()), trace_id),
        )
        await self._log_task_event("task_force_released", trace_id=trace_id, status=status)

    # ==================== 主入口 ====================

    async def deal(self) -> dict:
        task_name = self.data.get("task_name")
        if not task_name:
            return TaskScheduleResponse.fail_response(
                ErrorCode.VALIDATION_ERROR, "task_name is required"
            )

        try:
            task_name = TaskUtils.validate_task_name(task_name)
        except TaskValidationError as e:
            return TaskScheduleResponse.fail_response(ErrorCode.VALIDATION_ERROR, str(e))

        date_str = self.data.get("date_string") or datetime.now(
            ZoneInfo(self.config.timezone)
        ).strftime("%Y-%m-%d")

        handler = self.get_handler(task_name)
        if not handler:
            return TaskScheduleResponse.fail_response(
                ErrorCode.UNKNOWN_TASK,
                f"Unknown task: {task_name}. "
                f"Available tasks: {', '.join(self.list_registered_tasks())}",
            )

        return await self._run_with_guard(
            task_name,
            date_str,
            lambda: handler(self),
        )


__all__ = ["TaskScheduler"]
