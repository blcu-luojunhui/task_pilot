"""Chat 领域模块：会话与消息持久化、对话编排、ChatTurnRunner 轻量 Loop。"""

from .ids import generate_conversation_id
from .repository import (
    ChatRepository,
    ConversationStatus,
    MSG_STATUS_COMPLETED,
    MSG_STATUS_PENDING_CONFIRMATION,
    MSG_STATUS_REJECTED,
    MSG_STATUS_CANCELLED,
)
from .risk import ToolRisk, TOOL_RISK_REGISTRY, DEFAULT_RISK, CHAT_MODE_TOOLS, get_tool_risk, is_high_risk, is_chat_mode_tool
from .events import ChatEventType
from .runner import ChatTurnRunner, ChatTurnResult
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
    "CHAT_MODE_TOOLS",
    "get_tool_risk",
    "is_high_risk",
    "is_chat_mode_tool",
    "ChatEventType",
    "ChatTurnRunner",
    "ChatTurnResult",
    "ChatService",
    "TaskInvoker",
    "generate_conversation_id",
]
