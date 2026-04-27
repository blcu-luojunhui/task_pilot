"""
任务生命周期管理器

提供分布式环境下的协程生命周期管理，支持：
- 进程内任务注册表
- 基于 MySQL 的跨进程取消信号
- 轮询机制检测取消请求
- 优雅关闭时取消所有任务
"""

import asyncio
import logging
from typing import Dict, Optional

from src.core.database import DatabaseManager
from src.jobs.task_config import TaskStatus, TaskConstants

logger = logging.getLogger(__name__)


class TaskLifecycleManager:
    """任务生命周期管理器（单例）"""

    _instance: Optional["TaskLifecycleManager"] = None

    def __init__(
        self,
        db_client: DatabaseManager,
        poll_interval: float = 5.0,
        force_kill_timeout: float = 10.0,
    ):
        self._registry: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._db = db_client
        self._poll_interval = poll_interval
        self._force_kill_timeout = force_kill_timeout
        self._poll_task: Optional[asyncio.Task] = None
        self._shutting_down = False

    @classmethod
    def initialize(
        cls,
        db_client: DatabaseManager,
        poll_interval: float = 5.0,
        force_kill_timeout: float = 10.0,
    ) -> "TaskLifecycleManager":
        if cls._instance is None:
            cls._instance = cls(db_client, poll_interval, force_kill_timeout)
            logger.info(
                f"TaskLifecycleManager initialized with poll_interval={poll_interval}s"
            )
        return cls._instance

    @classmethod
    def get_instance(cls) -> Optional["TaskLifecycleManager"]:
        return cls._instance

    async def register(self, trace_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            self._registry[trace_id] = task
            logger.debug(f"Task registered: {trace_id}, total={len(self._registry)}")

    async def unregister(self, trace_id: str) -> None:
        async with self._lock:
            if trace_id in self._registry:
                del self._registry[trace_id]
                logger.debug(
                    f"Task unregistered: {trace_id}, total={len(self._registry)}"
                )

    async def cancel_local(self, trace_id: str) -> bool:
        async with self._lock:
            task = self._registry.get(trace_id)
            if not task:
                return False
            if task.done():
                return False
            logger.info(f"Cancelling task: {trace_id}")
            task.cancel()

        try:
            await asyncio.wait_for(task, timeout=self._force_kill_timeout)
        except asyncio.CancelledError:
            logger.info(f"Task cancelled successfully: {trace_id}")
        except asyncio.TimeoutError:
            logger.warning(
                f"Task did not respond to cancellation within "
                f"{self._force_kill_timeout}s: {trace_id}"
            )
        except Exception as e:
            logger.error(f"Error while waiting for task cancellation: {trace_id}, {e}")

        return True

    async def _poll_loop(self) -> None:
        logger.info("Task lifecycle polling loop started")
        table = TaskConstants.TASK_TABLE

        while not self._shutting_down:
            try:
                rows = await self._db.async_fetch(
                    f"SELECT trace_id FROM {table} WHERE task_status = %s",
                    params=(TaskStatus.CANCEL_REQUESTED,),
                )

                if rows:
                    async with self._lock:
                        local_trace_ids = set(self._registry.keys())

                    for row in rows:
                        trace_id = row["trace_id"]
                        if trace_id in local_trace_ids:
                            logger.info(
                                f"Cancel signal detected for task: {trace_id}"
                            )
                            await self.cancel_local(trace_id)

            except Exception as e:
                logger.exception(f"Error in poll loop: {e}")

            await asyncio.sleep(self._poll_interval)

        logger.info("Task lifecycle polling loop stopped")

    async def start_polling(self) -> None:
        if self._poll_task is not None:
            logger.warning("Polling already started")
            return

        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="task_lifecycle_poll"
        )
        logger.info("Task lifecycle polling started")

    async def stop_polling(self) -> None:
        if self._poll_task is None:
            return

        self._shutting_down = True
        self._poll_task.cancel()

        try:
            await self._poll_task
        except asyncio.CancelledError:
            pass

        self._poll_task = None
        logger.info("Task lifecycle polling stopped")

    async def shutdown(self, timeout: float = 30.0) -> None:
        logger.info("TaskLifecycleManager shutting down...")

        async with self._lock:
            tasks = list(self._registry.values())
            trace_ids = list(self._registry.keys())

        if tasks:
            logger.info(f"Cancelling {len(tasks)} running tasks: {trace_ids}")

            for task in tasks:
                if not task.done():
                    task.cancel()

            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout,
                )
                logger.info("All tasks cancelled successfully")
            except asyncio.TimeoutError:
                logger.warning(
                    f"Some tasks did not finish within {timeout}s timeout"
                )
        else:
            logger.info("No running tasks to cancel")

        await self.stop_polling()
        logger.info("TaskLifecycleManager shutdown complete")


__all__ = ["TaskLifecycleManager"]
