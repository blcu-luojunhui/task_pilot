"""Chat 领域模块：会话与消息持久化、对话编排。"""

from .ids import generate_conversation_id
from .repository import (
    ChatRepository,
    ConversationStatus,
    MSG_STATUS_COMPLETED,
    MSG_STATUS_PENDING_CONFIRMATION,
    MSG_STATUS_REJECTED,
    MSG_STATUS_CANCELLED,
)
from .risk import ToolRisk, TOOL_RISK_REGISTRY, DEFAULT_RISK, get_tool_risk, is_high_risk
from .events import ChatEventType
from .service import ChatService
from .task_invoker import TaskInvoker

__all__ = [
    "ChatRepository",
    "ConversationStatus",
    "MSG_STATUS_COMPLETED",
    "MSG_STATUS_PENDING_CONFIRMATION",
    "MSG_STATUS_REJECTED",
    "MSG_STATUS_CANCELLED",
    "ToolRisk",
    "TOOL_RISK_REGISTRY",
    "DEFAULT_RISK",
    "get_tool_risk",
    "is_high_risk",
    "ChatEventType",
    "ChatService",
    "TaskInvoker",
    "generate_conversation_id",
]
