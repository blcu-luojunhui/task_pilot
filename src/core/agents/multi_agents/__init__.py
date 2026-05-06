"""
Multi-Agent Module - 多 Agent 系统（预留）
"""

from .coordinator import MultiAgentCoordinator
from .communication import MessageType, Message, CommunicationChannel

__all__ = [
    "MultiAgentCoordinator",
    "MessageType",
    "Message",
    "CommunicationChannel",
]
