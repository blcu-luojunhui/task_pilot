from dataclasses import dataclass


@dataclass
class TaskConfig:
    """任务配置"""

    timeout: int  # 超时时间（秒）
    max_concurrent: int = 5  # 最大并发数
    retry_times: int = 0  # 重试次数
    retryable: bool = True  # 是否可重试
    alert_on_failure: bool = True  # 失败时是否告警


class TaskStatus:
    """任务状态常量"""

    INIT = 0
    PROCESSING = 1
    SUCCESS = 2
    CANCELLED = 3
    CANCEL_REQUESTED = 4
    FAILED = 99


class TaskConstants:
    """任务系统常量"""

    DEFAULT_TIMEOUT = 1800
    DEFAULT_MAX_CONCURRENT = 5
    DEFAULT_RETRY_TIMES = 0

    # 数据库表名（可通过配置覆盖）
    TASK_TABLE = "task_manager"


# 任务配置映射（业务项目中注册具体任务）
TASK_CONFIGS = {}


def get_task_config(task_name: str) -> TaskConfig:
    """获取任务配置，如果不存在则返回默认配置"""
    return TASK_CONFIGS.get(
        task_name,
        TaskConfig(
            timeout=TaskConstants.DEFAULT_TIMEOUT,
            max_concurrent=TaskConstants.DEFAULT_MAX_CONCURRENT,
            retry_times=TaskConstants.DEFAULT_RETRY_TIMES,
        ),
    )


__all__ = [
    "TaskConfig",
    "TaskStatus",
    "TaskConstants",
    "TASK_CONFIGS",
    "get_task_config",
]
