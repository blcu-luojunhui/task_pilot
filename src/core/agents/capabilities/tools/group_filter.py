"""工具分组白名单过滤。"""
from __future__ import annotations

from typing import Iterable, List, Optional

from src.core.agents.capabilities.skills.model import Skill


def filter_tools_by_groups(
    tools: Iterable[Skill],
    allowed_groups: Optional[List[str]] = None,
    exclude_tools: Optional[List[str]] = None,
) -> List[Skill]:
    """按组白名单 + 工具名黑名单过滤。

    allowed_groups=None 表示不限制（放行全部）。
    组名取自 skill.domain。
    """
    exclude = set(exclude_tools or [])
    result: List[Skill] = []
    for t in tools:
        if t.name in exclude:
            continue
        if allowed_groups is not None:
            group = getattr(t, "domain", None) or "general"
            if group not in allowed_groups:
                continue
        result.append(t)
    return result


__all__ = ["filter_tools_by_groups"]
