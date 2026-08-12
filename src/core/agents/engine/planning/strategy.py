"""决策策略抽象 — 可插拔的 Agent 决策循环算法"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ...state import AgentLoopState
    from ..loop import Think, Act, Observe
    from ...runtime.harness.approval import ApprovalPolicy


@dataclass
class StepOutput:
    """单步执行产出 — 策略 run_step 的返回值"""

    assistant_message: Optional[Dict[str, Any]] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason_override: Optional[Any] = None  # 策略直接设 stop_reason


@dataclass
class StrategyContext:
    """策略可访问的运行时句柄，避免策略直接耦合 Harness"""

    thinker: "Think"
    actor: "Act"
    observer: "Observe"
    approval_policy: Optional["ApprovalPolicy"] = None


class DecisionStrategy(Protocol):
    """可插拔的决策策略协议。

    策略负责决定"每一步 Think → Act → Observe 如何执行"，
    Harness 保留对生命周期、budget、feedback 和事件的完全控制。
    """

    name: str

    async def on_run_start(self, state: "AgentLoopState", ctx: StrategyContext) -> None:
        """run 开始时的初始化钩子（如 PlanExecute 生成 plan）"""
        ...

    async def run_step(self, state: "AgentLoopState", ctx: StrategyContext) -> StepOutput:
        """执行一步决策，返回 assistant_message 与 tool_results"""
        ...

    async def on_step_end(self, state: "AgentLoopState", ctx: StrategyContext, output: StepOutput) -> None:
        """每步结束后的钩子（如反思生成）"""
        ...
