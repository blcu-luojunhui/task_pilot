"""
核心类型定义 - Agent 的基础数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(str, Enum):
    """动作类型"""
    TOOL_CALL = "tool_call"
    SKILL_CALL = "skill_call"
    ANSWER = "answer"
    DELEGATE = "delegate"
    WAIT = "wait"


class ThoughtType(str, Enum):
    """思考类型"""
    REASONING = "reasoning"
    PLANNING = "planning"
    REFLECTION = "reflection"
    OBSERVATION = "observation"


@dataclass
class Thought:
    """Agent 的思考过程"""
    type: ThoughtType
    content: str
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """Agent 的动作"""
    type: ActionType
    target: str  # tool/skill name or answer text
    parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """执行结果观察"""
    action: Action
    result: Any
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """单步执行记录"""
    step_number: int
    thought: Optional[Thought] = None
    action: Optional[Action] = None
    observation: Optional[Observation] = None
