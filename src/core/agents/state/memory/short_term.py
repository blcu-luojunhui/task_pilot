"""
短期记忆 - 存储当前会话的上下文信息
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class ShortTermMemory:
    """短期记忆存储"""

    # 当前会话的消息历史
    messages: List[Dict[str, Any]] = field(default_factory=list)

    # 最近的工具调用结果
    recent_tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # 当前任务上下文
    current_context: Dict[str, Any] = field(default_factory=dict)

    # 会话元数据
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str, **metadata):
        """添加消息到历史"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **metadata
        })

    def add_tool_result(self, tool_name: str, result: Any, **metadata):
        """添加工具调用结果"""
        self.recent_tool_results.append({
            "tool": tool_name,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            **metadata
        })
        # 只保留最近 10 条
        if len(self.recent_tool_results) > 10:
            self.recent_tool_results = self.recent_tool_results[-10:]

    def clear(self):
        """清空短期记忆"""
        self.messages.clear()
        self.recent_tool_results.clear()
        self.current_context.clear()
