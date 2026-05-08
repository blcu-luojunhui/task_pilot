"""
Harness Runner - 主运行入口（DEPRECATED）

.. deprecated::
    此类是早期备选 runner 实现，未接入主链路。
    当前主链路使用 AgentLoopRunner + AgentLoopHarness。
"""

import warnings
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ...engine.types import Step, Action, Observation
from ...execution import ExecutionResult


@dataclass
class RunnerConfig:
    """Runner 配置"""

    max_steps: int = 10
    timeout_seconds: float = 300.0
    enable_tracing: bool = True
    enable_logging: bool = True


class HarnessRunner:
    """
    Harness 主运行器（DEPRECATED）

    .. deprecated::
        使用 AgentLoopRunner + AgentLoopHarness 代替。
    """

    def __init__(self, config: Optional[RunnerConfig] = None):
        warnings.warn(
            "HarnessRunner is deprecated, use AgentLoopRunner + AgentLoopHarness instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config = config or RunnerConfig()
        self.steps: List[Step] = []
        self.hooks = []

    def add_hook(self, hook):
        """添加 hook"""
        self.hooks.append(hook)

    async def run(
        self, agent, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        运行 Agent

        Args:
            agent: Agent 实例
            goal: 目标任务
            context: 上下文

        Returns:
            执行结果
        """
        # 触发 on_start hooks
        for hook in self.hooks:
            await hook.on_start({"goal": goal, "context": context})

        # 执行 agent
        result = await agent.run(goal, context)

        # 触发 on_complete hooks
        for hook in self.hooks:
            await hook.on_complete({"result": result})

        return result
