"""Protocol models for agent messages"""

from typing import Any, Dict
from dataclasses import dataclass


@dataclass
class ToolCall:
    """Represents a tool call in the agent protocol"""
    id: str
    name: str
    input: Dict[str, Any]
