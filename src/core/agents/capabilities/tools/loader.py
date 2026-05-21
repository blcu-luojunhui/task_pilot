"""Agent tool loader utilities"""

from importlib import import_module
from typing import Iterable, List, Optional

TOOL_AREAS = {
    "database": "src.core.agents.capabilities.tools.database",
    "http": "src.core.agents.capabilities.tools.http",
    "task": "src.core.agents.capabilities.tools.task",
    "utils": "src.core.agents.capabilities.tools.utils",
    "chat_ops": "src.core.agents.capabilities.tools.chat_ops",
}
DEFAULT_TOOL_AREAS = ("utils",)


def load_agentic_tools(areas: Optional[Iterable[str]] = None) -> List[str]:
    """
    显式加载 Agent 工具区域。

    默认只加载不依赖 infra 的 utils；database/http/task 需要调用方按需启用。
    """
    selected = tuple(areas) if areas is not None else DEFAULT_TOOL_AREAS
    loaded = []

    for area in selected:
        if area not in TOOL_AREAS:
            raise ValueError(f"Unknown agentic tool area: {area}")
        import_module(TOOL_AREAS[area])
        loaded.append(area)

    return loaded
