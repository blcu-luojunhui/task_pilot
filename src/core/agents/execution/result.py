"""
执行结果结构定义
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class ExecutionStatus(str, Enum):
    """执行状态"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


@dataclass
class ExecutionResult:
    """执行结果"""

    status: ExecutionStatus
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolExecutionResult(ExecutionResult):
    """工具执行结果"""

    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillExecutionResult(ExecutionResult):
    """技能执行结果"""

    skill_name: str = ""
    skill_input: Dict[str, Any] = field(default_factory=dict)
