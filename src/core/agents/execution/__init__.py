"""
Execution Layer - 执行层

负责任务调度和执行结果：
- dispatcher: 统一调度
- result: 执行结果
"""

from .result import (
    ExecutionStatus,
    ExecutionResult,
    ToolExecutionResult,
    SkillExecutionResult,
)
from .dispatcher import Dispatcher

__all__ = [
    "ExecutionStatus",
    "ExecutionResult",
    "ToolExecutionResult",
    "SkillExecutionResult",
    "Dispatcher",
]
