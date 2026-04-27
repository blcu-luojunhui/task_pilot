from datetime import datetime
from typing import Callable, Dict, Optional

from src.core.config import GlobalConfigSettings
from src.jobs.task_config import TaskStatus
from src.jobs.task_utils import TaskValidationError


_TASK_HANDLER_REGISTRY: Dict[str, Callable] = {}


def register(task_name: str):
    """装饰器：注册任务处理器"""
    def decorator(func):
        _TASK_HANDLER_REGISTRY[task_name] = func
        return func
    return decorator


class TaskHandler:
    """
    任务处理器基类

    使用 @register("task_name") 装饰器注册任务处理器。
    业务项目中继承此类并添加具体的任务方法。

    示例：
        @register("example_task")
        async def _example_handler(self) -> int:
            # 你的业务逻辑
            return TaskStatus.SUCCESS
    """

    _handlers = _TASK_HANDLER_REGISTRY

    def __init__(
        self,
        data: dict,
        log_service,
        db_client,
        trace_id: str,
        config: GlobalConfigSettings,
    ):
        self.data = data
        self.log_client = log_service
        self.db_client = db_client
        self.trace_id = trace_id
        self.config = config

    @classmethod
    def get_handler(cls, task_name: str) -> Optional[Callable]:
        return cls._handlers.get(task_name)

    @classmethod
    def list_registered_tasks(cls) -> list:
        return list(cls._handlers.keys())

    async def _log_task_event(self, event_type: str, **kwargs):
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "trace_id": self.trace_id,
            "event_type": event_type,
            "task": self.data.get("task_name"),
            **kwargs,
        }
        await self.log_client.log(contents=log_data)


__all__ = ["TaskHandler", "register"]
