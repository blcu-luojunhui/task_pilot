"""
统一注册器 - 整合 tools 和 skills 的注册机制
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from .skills import Skill, SkillRegistry as BaseSkillRegistry, SkillType, RiskLevel


@dataclass
class CapabilityRegistry:
    """
    统一的能力注册器

    整合 tools 和 skills 的注册，提供统一的接口
    """

    _skill_registry: BaseSkillRegistry = field(default_factory=BaseSkillRegistry)
    _tools: Dict[str, Callable] = field(default_factory=dict)

    def register_skill(self, skill: Skill):
        """注册 skill"""
        self._skill_registry.register(skill)

    def register_tool(self, name: str, handler: Callable, **metadata):
        """注册 tool（会自动转换为 skill）"""
        # 将 tool 转换为 skill
        skill = Skill(
            skill_id=f"tool_{name}",
            name=name,
            description=metadata.get("description", ""),
            skill_type=SkillType.EXECUTABLE,
            handler=handler,
            parameters=metadata.get("parameters", {}),
            risk_level=metadata.get("risk_level", RiskLevel.READ),
            **metadata
        )
        self.register_skill(skill)
        self._tools[name] = handler

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取 skill"""
        return self._skill_registry.get(name)

    def list_skills(self, **filters) -> List[Skill]:
        """列出所有 skills"""
        return self._skill_registry.list(**filters)

    def list_tools(self) -> List[str]:
        """列出所有 tools"""
        return list(self._tools.keys())

    @property
    def skill_registry(self) -> BaseSkillRegistry:
        """获取底层 skill registry"""
        return self._skill_registry


# 全局注册器实例
_global_registry: Optional[CapabilityRegistry] = None


def get_global_capability_registry() -> CapabilityRegistry:
    """获取全局注册器"""
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry()
    return _global_registry


__all__ = ["CapabilityRegistry", "get_global_capability_registry"]
