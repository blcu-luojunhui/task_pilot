"""
任务系统异常定义和工具类
"""

import re
from typing import Optional


class TaskError(Exception):
    """任务错误基类"""

    def __init__(self, message: str, retryable: bool = True, task_name: Optional[str] = None):
        self.message = message
        self.retryable = retryable
        self.task_name = task_name
        super().__init__(message)


class TaskValidationError(TaskError):
    """任务验证错误（不可重试）"""

    def __init__(self, message: str, task_name: Optional[str] = None):
        super().__init__(message, retryable=False, task_name=task_name)


class TaskTimeoutError(TaskError):
    """任务超时错误（可重试）"""

    def __init__(self, message: str, task_name: Optional[str] = None):
        super().__init__(message, retryable=True, task_name=task_name)


class TaskConcurrencyError(TaskError):
    """任务并发限制错误（不可重试）"""

    def __init__(self, message: str, task_name: Optional[str] = None):
        super().__init__(message, retryable=False, task_name=task_name)


class TaskLockError(TaskError):
    """任务锁获取失败（不可重试）"""

    def __init__(self, message: str, task_name: Optional[str] = None):
        super().__init__(message, retryable=False, task_name=task_name)


class TaskCancelledError(TaskError):
    """任务被取消（不可重试）"""

    def __init__(self, message: str, task_name: Optional[str] = None):
        super().__init__(message, retryable=False, task_name=task_name)


class TaskUtils:
    """任务工具类"""

    @staticmethod
    def validate_table_name(table: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", table):
            raise ValueError(f"Invalid table name: {table}")
        return table

    @staticmethod
    def validate_task_name(task_name: str) -> str:
        if not task_name or not isinstance(task_name, str):
            raise TaskValidationError("task_name must be a non-empty string")
        if not re.match(r"^[a-zA-Z0-9_]+$", task_name):
            raise TaskValidationError(f"Invalid task_name format: {task_name}")
        return task_name

    @staticmethod
    def format_error_detail(error: Exception) -> dict:
        import traceback

        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "retryable": getattr(error, "retryable", False),
        }


__all__ = [
    "TaskError",
    "TaskValidationError",
    "TaskTimeoutError",
    "TaskConcurrencyError",
    "TaskLockError",
    "TaskCancelledError",
    "TaskUtils",
]
