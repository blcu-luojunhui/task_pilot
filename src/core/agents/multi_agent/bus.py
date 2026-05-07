"""
消息总线

实现 Agent 间的消息路由和分发
"""

import asyncio
from typing import Any, Dict, List, Callable, Awaitable, Optional
from collections import defaultdict
import logging

from .protocol import Message, MessageType, MessagePriority

logger = logging.getLogger(__name__)

MessageHandler = Callable[[Message], Awaitable[None]]


class MessageBus:
    """消息总线"""

    def __init__(self, max_history: int = 1000):
        """
        初始化消息总线

        Args:
            max_history: 最大消息历史记录数
        """
        # agent_id -> queue
        self._queues: Dict[str, asyncio.Queue] = {}

        # message_type -> handlers
        self._handlers: Dict[MessageType, List[MessageHandler]] = defaultdict(list)

        # 消息历史
        self._history: List[Message] = []
        self._max_history = max_history

        # 统计信息
        self._stats = {
            "total_messages": 0,
            "messages_by_type": defaultdict(int),
            "messages_by_agent": defaultdict(int),
        }

    def register_agent(self, agent_id: str) -> asyncio.Queue:
        """
        注册 Agent

        Args:
            agent_id: Agent ID

        Returns:
            Agent 的消息队列
        """
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
            logger.info(f"Agent registered: {agent_id}")
        return self._queues[agent_id]

    def unregister_agent(self, agent_id: str):
        """
        注销 Agent

        Args:
            agent_id: Agent ID
        """
        if agent_id in self._queues:
            del self._queues[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")

    def subscribe(self, message_type: MessageType, handler: MessageHandler):
        """
        订阅消息类型

        Args:
            message_type: 消息类型
            handler: 消息处理器
        """
        self._handlers[message_type].append(handler)
        logger.info(f"Handler subscribed to {message_type}")

    def unsubscribe(self, message_type: MessageType, handler: MessageHandler):
        """
        取消订阅

        Args:
            message_type: 消息类型
            handler: 消息处理器
        """
        if handler in self._handlers[message_type]:
            self._handlers[message_type].remove(handler)

    async def send(self, message: Message):
        """
        发送消息

        Args:
            message: 消息对象
        """
        # 检查消息是否过期
        if message.is_expired():
            logger.warning(f"Message {message.id} expired, not sending")
            return

        # 记录历史
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        # 更新统计
        self._stats["total_messages"] += 1
        self._stats["messages_by_type"][message.type] += 1
        self._stats["messages_by_agent"][message.sender] += 1

        # 触发处理器
        for handler in self._handlers.get(message.type, []):
            try:
                asyncio.create_task(handler(message))
            except Exception as e:
                logger.error(f"Handler error: {e}")

        # 路由消息
        if message.receiver == "*":
            # 广播
            await self._broadcast(message)
        else:
            # 点对点
            await self._send_to_agent(message)

    async def _broadcast(self, message: Message):
        """广播消息到所有 Agent"""
        for agent_id, queue in self._queues.items():
            if agent_id != message.sender:  # 不发送给自己
                try:
                    await queue.put(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast to {agent_id}: {e}")

    async def _send_to_agent(self, message: Message):
        """发送消息到指定 Agent"""
        if message.receiver in self._queues:
            try:
                await self._queues[message.receiver].put(message)
            except Exception as e:
                logger.error(f"Failed to send to {message.receiver}: {e}")
        else:
            logger.warning(f"Agent {message.receiver} not found")

    async def receive(
        self,
        agent_id: str,
        timeout: Optional[float] = None,
        priority_filter: Optional[MessagePriority] = None,
    ) -> Message:
        """
        接收消息

        Args:
            agent_id: Agent ID
            timeout: 超时时间（秒）
            priority_filter: 优先级过滤

        Returns:
            消息对象

        Raises:
            ValueError: 如果 Agent 未注册
            asyncio.TimeoutError: 如果超时
        """
        queue = self._queues.get(agent_id)
        if not queue:
            raise ValueError(f"Agent {agent_id} not registered")

        if timeout:
            message = await asyncio.wait_for(queue.get(), timeout=timeout)
        else:
            message = await queue.get()

        # 优先级过滤
        if priority_filter and message.priority < priority_filter:
            # 放回队列，继续等待
            await queue.put(message)
            return await self.receive(agent_id, timeout, priority_filter)

        return message

    def get_history(
        self,
        agent_id: Optional[str] = None,
        message_type: Optional[MessageType] = None,
        limit: int = 100,
    ) -> List[Message]:
        """
        获取消息历史

        Args:
            agent_id: 可选的 Agent ID 过滤
            message_type: 可选的消息类型过滤
            limit: 返回的最大消息数

        Returns:
            消息列表
        """
        history = self._history

        if agent_id:
            history = [m for m in history if m.sender == agent_id or m.receiver == agent_id]

        if message_type:
            history = [m for m in history if m.type == message_type]

        return history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_messages": self._stats["total_messages"],
            "messages_by_type": dict(self._stats["messages_by_type"]),
            "messages_by_agent": dict(self._stats["messages_by_agent"]),
            "active_agents": len(self._queues),
            "handlers": {
                msg_type.value: len(handlers) for msg_type, handlers in self._handlers.items()
            },
        }

    def clear_history(self):
        """清空消息历史"""
        self._history.clear()

    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "total_messages": 0,
            "messages_by_type": defaultdict(int),
            "messages_by_agent": defaultdict(int),
        }


__all__ = ["MessageBus", "MessageHandler"]
