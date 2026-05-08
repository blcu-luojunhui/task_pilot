"""
统一调度入口 - 协调 executor 和 router

.. deprecated::
    此模块尚未接入主执行链路，暂不可用。当前的编排路径是：
    Agent.run() -> AgentLoopRunner -> AgentLoopHarness。
"""

import warnings
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .result import ExecutionResult, ExecutionStatus


@dataclass
class Dispatcher:
    """
    统一调度器（待接入主链路）

    .. deprecated::
        当前未接入主执行路径。编排由 AgentLoopRunner + AgentLoopHarness 完成。
    """

    def __init__(self, executor=None, router=None):
        self.executor = executor
        self.router = router

    async def dispatch(
        self,
        action_type: str,
        target: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        统一调度入口

        Args:
            action_type: 动作类型 (tool_call, skill_call, etc.)
            target: 目标名称
            parameters: 参数
            context: 上下文

        Returns:
            执行结果
        """
        # 如果有 router，先进行路由判断
        if self.router:
            route_result = await self.router.route(action_type, target, context)
            if route_result:
                target = route_result.get("target", target)
                parameters = route_result.get("parameters", parameters)

        # 执行
        if self.executor:
            return await self.executor.execute(target, parameters, context)

        return ExecutionResult(
            status=ExecutionStatus.FAILED, output=None, error="No executor available"
        )
