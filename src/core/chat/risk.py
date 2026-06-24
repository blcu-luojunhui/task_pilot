from enum import IntEnum
from typing import Dict


class ToolRisk(IntEnum):
    LOW = 0
    HIGH = 1


TOOL_RISK_REGISTRY: Dict[str, ToolRisk] = {
    "plan_tasks": ToolRisk.LOW,
    "list_recent_tasks": ToolRisk.LOW,
    "run_task": ToolRisk.HIGH,
}

DEFAULT_RISK = ToolRisk.HIGH


def get_tool_risk(tool_name: str) -> ToolRisk:
    return TOOL_RISK_REGISTRY.get(tool_name, DEFAULT_RISK)


def is_high_risk(tool_name: str) -> bool:
    return get_tool_risk(tool_name) == ToolRisk.HIGH


__all__ = [
    "ToolRisk",
    "TOOL_RISK_REGISTRY",
    "DEFAULT_RISK",
    "get_tool_risk",
    "is_high_risk",
]
