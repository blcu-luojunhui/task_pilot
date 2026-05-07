"""
Core module - Agent 控制层

包含：
- agent: Agent 主类
- runner: AgentLoopRunner（组装器）
- loop: Think-Act-Observe 循环
- types: 核心类型定义
- prompting: Prompt 工程组件
- lifecycle: 生命周期管理
"""

from .agent import Agent, AgentConfig
from .runner import AgentLoopRunner
from .loop import Think, Act, Observe, AssistantPlanner
from .types import (
    ActionType,
    ThoughtType,
    Thought,
    Action,
    Observation,
    Step,
)
from .prompting import PromptAssembler, KnowledgeSelector
from .lifecycle import LifecycleManager

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentLoopRunner",
    "Think",
    "Act",
    "Observe",
    "AssistantPlanner",
    "ActionType",
    "ThoughtType",
    "Thought",
    "Action",
    "Observation",
    "Step",
    "PromptAssembler",
    "KnowledgeSelector",
    "LifecycleManager",
]
