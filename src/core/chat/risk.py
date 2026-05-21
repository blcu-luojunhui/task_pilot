from enum import IntEnum
from typing import Dict


class ToolRisk(IntEnum):
    LOW = 0
    HIGH = 1


TOOL_RISK_REGISTRY: Dict[str, ToolRisk] = {
    "plan_tasks": ToolRisk.LOW,
    "list_recent_tasks": ToolRisk.LOW,
    "escalate_to_agent": ToolRisk.LOW,
    "run_task": ToolRisk.HIGH,
}

DEFAULT_RISK = ToolRisk.HIGH

# chat 模式（未升级）暴露的工具白名单
CHAT_MODE_TOOLS = frozenset({"escalate_to_agent", "list_recent_tasks"})


def get_tool_risk(tool_name: str) -> ToolRisk:
    return TOOL_RISK_REGISTRY.get(tool_name, DEFAULT_RISK)


def is_high_risk(tool_name: str) -> bool:
    return get_tool_risk(tool_name) == ToolRisk.HIGH


def is_chat_mode_tool(tool_name: str) -> bool:
    return tool_name in CHAT_MODE_TOOLS


__all__ = [
    "ToolRisk",
    "TOOL_RISK_REGISTRY",
    "DEFAULT_RISK",
    "CHAT_MODE_TOOLS",
    "get_tool_risk",
    "is_high_risk",
    "is_chat_mode_tool",
]
