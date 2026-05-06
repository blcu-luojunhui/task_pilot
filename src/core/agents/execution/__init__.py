"""
Execution Layer - 执行层

负责任务的执行和路由：
- executor: 执行器
- router: 路由器
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
