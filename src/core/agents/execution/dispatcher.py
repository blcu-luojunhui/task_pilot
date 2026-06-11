"""
统一调度入口 — Agent 执行的唯一门面。

Dispatcher 委托给现有的 AgentLoopRunner（单代理）和 MultiAgentCoordinator（多代理），
不重复实现编排逻辑，只提供收口的入口点。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .result import ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from src.core.agents.engine.runner import AgentLoopRunner
    from src.core.agents.multi_agents.coordinator import MultiAgentCoordinator

logger = logging.getLogger(__name__)


@dataclass
class Dispatcher:
    """
    统一调度器 — 单代理与多代理执行的统一门面。

    run_single 内部委托给 AgentLoopRunner，run_multi 内部委托给 MultiAgentCoordinator。
    此处不做重复编排，只为调用方提供稳定的入口。
    """

    runner: "Optional[AgentLoopRunner]" = None
    coordinator: "Optional[MultiAgentCoordinator]" = None

    async def run_single(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        执行单个 Agent 任务。

        内部委托给 AgentLoopRunner.run()，将其 AgentLoopResult 转换为统一的
        ExecutionResult 返回。
        """
        if not self.runner:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error="Dispatcher.run_single: no AgentLoopRunner configured",
            )
        try:
            loop_result = await self.runner.run(
                goal=goal,
                messages=messages,
                metadata=metadata,
                trace_id=trace_id,
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS if loop_result.success else ExecutionStatus.FAILED,
                output=loop_result.final_answer,
                error=None if loop_result.success else (loop_result.stop_reason.value if loop_result.stop_reason else None),
                metadata={
                    "trace_id": loop_result.trace_id,
                    "total_steps": loop_result.total_steps,
                    "tool_calls_count": loop_result.tool_calls_count,
                    "duration_seconds": loop_result.duration_seconds,
                    "token_usage": loop_result.token_usage,
                },
            )
        except Exception as exc:
            logger.exception("Dispatcher.run_single failed: %s", exc)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=str(exc),
            )

    async def run_multi(
        self,
        goal: str,
        agents: Optional[List[Any]] = None,
        strategy: str = "sequential",
    ) -> ExecutionResult:
        """
        执行多 Agent 协作任务。

        内部委托给 MultiAgentCoordinator.coordinate()。
        """
        if not self.coordinator:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error="Dispatcher.run_multi: no MultiAgentCoordinator configured",
            )
        try:
            multi_result = await self.coordinator.coordinate(
                goal=goal,
                agents=agents,
                strategy=strategy,
            )
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS if multi_result.get("success") else ExecutionStatus.FAILED,
                output=multi_result.get("final_answer"),
                error=multi_result.get("error"),
                metadata=dict(multi_result),
            )
        except Exception as exc:
            logger.exception("Dispatcher.run_multi failed: %s", exc)
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=str(exc),
            )
