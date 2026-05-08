"""
Multi-Agent Module - 多 Agent 系统

提供多 Agent 协作的完整解决方案：
- protocol: 消息协议
- bus: 消息总线
- coordinator: 协调器
"""

from .protocol import Message, MessageType, MessagePriority
from .bus import MessageBus, MessageHandler
from .coordinator import MultiAgentCoordinator, TaskAssignment

__all__ = [
    # Protocol
    "Message",
    "MessageType",
    "MessagePriority",
    # Bus
    "MessageBus",
    "MessageHandler",
    # Coordinator
    "MultiAgentCoordinator",
    "TaskAssignment",
]
