"""
Agent 间通信协议

定义 Agent 之间的消息格式和通信规范
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime
import uuid


class MessageType(str, Enum):
    """消息类型"""

    REQUEST = "request"  # 请求
    RESPONSE = "response"  # 响应
    BROADCAST = "broadcast"  # 广播
    NOTIFICATION = "notification"  # 通知
    TASK = "task"  # 任务分配
    RESULT = "result"  # 任务结果
    HEARTBEAT = "heartbeat"  # 心跳


class MessagePriority(int, Enum):
    """消息优先级"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class Message:
    """Agent 间消息"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.REQUEST
    sender: str = ""
    receiver: str = ""  # "*" 表示广播
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None  # 回复的消息 ID
    priority: MessagePriority = MessagePriority.NORMAL
    ttl: Optional[int] = None  # 消息存活时间（秒）

    def reply(self, content: Any, **metadata) -> "Message":
        """
        创建回复消息

        Args:
            content: 回复内容
            **metadata: 额外元数据

        Returns:
            回复消息
        """
        return Message(
            type=MessageType.RESPONSE,
            sender=self.receiver,
            receiver=self.sender,
            content=content,
            reply_to=self.id,
            metadata=metadata,
            priority=self.priority,
        )

    def is_expired(self) -> bool:
        """检查消息是否过期"""
        if self.ttl is None:
            return False
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "type": self.type.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
            "priority": self.priority.value,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建"""
        return cls(
            id=data["id"],
            type=MessageType(data["type"]),
            sender=data["sender"],
            receiver=data["receiver"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reply_to=data.get("reply_to"),
            priority=MessagePriority(data.get("priority", MessagePriority.NORMAL.value)),
            ttl=data.get("ttl"),
        )


__all__ = [
    "Message",
    "MessageType",
    "MessagePriority",
]
