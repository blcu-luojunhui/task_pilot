"""
Multi-Agent Communication - Agent 间通信（预留）
"""

from typing import Any, Dict
from dataclasses import dataclass
from enum import Enum


class MessageType(str, Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    NOTIFICATION = "notification"


@dataclass
class Message:
    """Agent 间消息"""
    type: MessageType
    sender: str
    receiver: str
    content: Any
    metadata: Dict[str, Any]


class CommunicationChannel:
    """通信通道"""

    async def send(self, message: Message):
        """发送消息"""
        pass

    async def receive(self) -> Message:
        """接收消息"""
        pass


__all__ = ["MessageType", "Message", "CommunicationChannel"]
