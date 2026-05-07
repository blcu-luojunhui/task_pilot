"""
Agent 生命周期管理

提供 Agent 的状态管理和生命周期控制
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, List
from datetime import datetime
import asyncio

from ..state.models import AgentState, StateTransition


class LifecycleManager:
    """Agent 生命周期管理器"""

    def __init__(self):
        self.state = AgentState.IDLE
        self.transitions: List[StateTransition] = []
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始不暂停
        self._stop_requested = False
        self._on_state_change: Optional[Callable] = None

    def can_transition(self, to_state: AgentState) -> bool:
        """检查是否可以转换到目标状态"""
        valid_transitions = {
            AgentState.IDLE: [AgentState.RUNNING],
            AgentState.RUNNING: [AgentState.PAUSED, AgentState.STOPPED, AgentState.ERROR],
            AgentState.PAUSED: [AgentState.RUNNING, AgentState.STOPPED],
            AgentState.STOPPED: [AgentState.IDLE],
            AgentState.ERROR: [AgentState.IDLE, AgentState.STOPPED],
        }
        return to_state in valid_transitions.get(self.state, [])

    def transition_to(self, to_state: AgentState, reason: Optional[str] = None):
        """
        转换状态

        Args:
            to_state: 目标状态
            reason: 转换原因

        Raises:
            ValueError: 如果不能转换到目标状态
        """
        if not self.can_transition(to_state):
            raise ValueError(
                f"Cannot transition from {self.state} to {to_state}"
            )

        # 记录转换
        transition = StateTransition(
            from_state=self.state,
            to_state=to_state,
            reason=reason
        )
        self.transitions.append(transition)

        # 更新状态
        old_state = self.state
        self.state = to_state

        # 触发回调
        if self._on_state_change:
            self._on_state_change(old_state, to_state)

        # 处理特殊状态
        if to_state == AgentState.PAUSED:
            self._pause_event.clear()
        elif to_state == AgentState.RUNNING:
            self._pause_event.set()
            self._stop_requested = False
        elif to_state == AgentState.STOPPED:
            self._stop_requested = True
            self._pause_event.set()  # 确保不会卡在暂停状态

    async def wait_if_paused(self):
        """如果暂停则等待"""
        await self._pause_event.wait()

    def is_stop_requested(self) -> bool:
        """是否请求停止"""
        return self._stop_requested

    def on_state_change(self, callback: Callable[[AgentState, AgentState], None]):
        """
        注册状态变化回调

        Args:
            callback: 回调函数，接收 (old_state, new_state) 参数
        """
        self._on_state_change = callback

    def get_history(self, limit: int = 10) -> List[StateTransition]:
        """
        获取状态转换历史

        Args:
            limit: 返回的最大记录数

        Returns:
            状态转换记录列表
        """
        return self.transitions[-limit:]

    def reset(self):
        """重置生命周期管理器"""
        self.state = AgentState.IDLE
        self.transitions.clear()
        self._pause_event.set()
        self._stop_requested = False


__all__ = [
    "AgentState",
    "StateTransition",
    "LifecycleManager",
]
