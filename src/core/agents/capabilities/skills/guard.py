"""
权限守卫

在工具执行前检查风险等级和访问权限
"""

from dataclasses import dataclass, field
from typing import Optional, Set

from .model import RiskLevel, Skill


@dataclass
class PermissionGuard:
    """工具执行权限守卫"""

    # 允许执行的风险等级（默认允许 READ 和 WRITE）
    allowed_levels: Set[RiskLevel] = field(
        default_factory=lambda: {RiskLevel.READ, RiskLevel.WRITE}
    )
    # 工具白名单（None 表示不限制）
    allowed_tools: Optional[Set[str]] = None
    # 工具黑名单
    blocked_tools: Set[str] = field(default_factory=set)

    def check(self, skill: Skill) -> Optional[str]:
        """
        检查工具是否允许执行。

        Returns:
            None if allowed, error message string if denied.
        """
        # 黑名单优先
        if skill.name in self.blocked_tools:
            return f"Tool '{skill.name}' is blocked by permission policy"

        # 白名单检查
        if self.allowed_tools is not None and skill.name not in self.allowed_tools:
            return f"Tool '{skill.name}' is not in the allowed tools list"

        # 风险等级检查
        if skill.risk_level not in self.allowed_levels:
            return (
                f"Tool '{skill.name}' requires risk level '{skill.risk_level.value}' "
                f"which is not permitted (allowed: {[l.value for l in self.allowed_levels]})"
            )

        return None


__all__ = ["PermissionGuard"]
